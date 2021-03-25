########
# Copyright (c) 2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os

from cloudify_common_sdk.utils import get_deployment_dir

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from .decorators import with_helm, prepare_aws
from .utils import (
    get_binary,
    copy_binary,
    helm_from_ctx,
    prepare_aws_env,
    is_using_existing,
    get_helm_executable_path,
    use_existing_repo_on_helm,
    create_temporary_env_of_helm,
    delete_temporary_env_of_helm)
from .constants import (
    HOST,
    NAME_FIELD,
    FLAGS_FIELD,
    VALUES_FILE,
    API_OPTIONS,
    HELM_CONFIG,
    CONFIGURATION,
    CLIENT_CONFIG,
    RESOURCE_CONFIG,
    EXECUTABLE_PATH,
    HELM_ENV_VARS_LIST,
    USE_EXTERNAL_RESOURCE)


@operation
def install_binary(ctx, **_):
    executable_path = ctx.node.properties.get(
        HELM_CONFIG, {}).get(EXECUTABLE_PATH, "")
    if executable_path:
        ctx.logger.warning('You are requesting to write a new file to {loc}. '
                           'If you do not have sufficient permissions, that '
                           'installation will fail.Please talk your system '
                           'administrator if using executable_path '
                           'property.'.format(loc=executable_path))
    else:
        executable_path = os.path.join(
            get_deployment_dir(ctx.deployment.id), 'helm')

    if is_using_existing(ctx):
        if not os.path.isfile(executable_path):
            raise NonRecoverableError(
                "Helm executable not found at {0}, cant use existing "
                "binary!".format(executable_path))
    else:
        if os.path.isfile(executable_path):
            ctx.logger.info(
                "Helm executable already found at {path};skipping "
                "installation of executable".format(path=executable_path))
        else:
            with get_binary(ctx) as binary:
                copy_binary(binary, executable_path)
    create_temporary_env_of_helm(ctx)
    ctx.instance.runtime_properties[
        EXECUTABLE_PATH] = executable_path


@operation
def uninstall_binary(ctx, **_):
    executable_path = get_helm_executable_path(ctx.node.properties,
                                          ctx.instance.runtime_properties)

    if os.path.isfile(executable_path) and not is_using_existing(ctx):
        ctx.logger.info("Removing executable: {0}".format(executable_path))
        os.remove(executable_path)
    delete_temporary_env_of_helm(ctx)


def prepare_args(ctx, flags=None):
    """
    Prepare arguments dictionary to helm  sdk function(like:helm.install,
    helm.repo_add).
    :param ctx: cloudify context.
    :param flags: flags that user passed - unique for install operation.
    :return arguments dictionary for helm.install function
    """
    flags = flags or []
    args_dict = {}
    args_dict.update(ctx.node.properties.get(RESOURCE_CONFIG, {}))
    args_dict[FLAGS_FIELD] = args_dict[FLAGS_FIELD] + flags
    # Pop local path of values_file, its not necessary parameter.
    args_dict.pop(VALUES_FILE, None)
    return args_dict


@operation
@with_helm()
@prepare_aws
def install_release(ctx,
                    helm,
                    kubeconfig=None,
                    values_file=None,
                    token=None,
                    env_vars=None,
                    **kwargs):
    """
    Execute helm install.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :param kubeconfig: kubeconfig path
    :param values_file: values file path
    :return output of `helm install` command
    """
    args_dict = prepare_args(ctx, kwargs.get(FLAGS_FIELD))
    output = helm.install(
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=ctx.node.properties.get(
            CLIENT_CONFIG, {}).get(CONFIGURATION, {}).get(API_OPTIONS, {}).get(
            HOST),
        additional_env=env_vars,
        **args_dict)
    ctx.instance.runtime_properties['install_output'] = output


@operation
@with_helm()
@prepare_aws
def uninstall_release(ctx,
                      helm,
                      kubeconfig=None,
                      token=None,
                      env_vars=None,
                      **kwargs):
    args_dict = prepare_args(ctx, kwargs.get(FLAGS_FIELD))
    helm.uninstall(
        kubeconfig=kubeconfig,
        token=token,
        apiserver=ctx.node.properties.get(
            CLIENT_CONFIG, {}).get(CONFIGURATION, {}).get(API_OPTIONS, {}).get(
            HOST),
        additional_env=env_vars,
        **args_dict)


@operation
@with_helm()
def add_repo(ctx, helm, **kwargs):
    if not use_existing_repo_on_helm(ctx, helm):
        args_dict = prepare_args(ctx, kwargs.get('flags'))
        helm.repo_add(**args_dict)


@operation
@with_helm()
def remove_repo(ctx, helm, **kwargs):
    if not ctx.node.properties.get(USE_EXTERNAL_RESOURCE):
        args_dict = prepare_args(ctx, kwargs.get(FLAGS_FIELD))
        helm.repo_remove(**args_dict)


@operation
def inject_env_properties(ctx, **_):
    for dir_property_name in [EXECUTABLE_PATH] + HELM_ENV_VARS_LIST:
        value = ctx.target.instance.runtime_properties.get(dir_property_name,
                                                           "")
        ctx.logger.info(
            "setting {property} to {value}".format(property=dir_property_name,
                                                   value=value))
        ctx.source.instance.runtime_properties[
            dir_property_name] = value


@operation
def update_repo(ctx, **kwargs):
    helm = helm_from_ctx(ctx)
    helm.repo_update(flags=kwargs.get(FLAGS_FIELD))


@operation
@with_helm(ignore_properties_values_file=True)
@prepare_aws
def upgrade_release(ctx,
                    helm,
                    chart='',
                    kubeconfig=None,
                    values_file=None,
                    set_values=None,
                    token=None,
                    flags=None,
                    env_vars=None,
                    **_):
    """
    Execute helm upgrade.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :param chart: The chart to upgrade the release with.
    :param kubeconfig: kubeconfig path.
    :param values_file: values file path.
    :return output of `helm upgrade` command
    """
    ctx.logger.debug(
        "Checking if used local packaged chart file, If local file used and "
        "the command failed check file access permissions.")
    if os.path.isfile(chart):
        ctx.logger.info("Local chart file: {path} found.".format(path=chart))
    output = helm.upgrade(
        release_name=ctx.node.properties.get(
            RESOURCE_CONFIG, {}).get(NAME_FIELD),
        chart=chart,
        flags=flags,
        set_values=set_values,
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=ctx.node.properties.get(
            CLIENT_CONFIG, {}).get(CONFIGURATION, {}).get(API_OPTIONS, {}).get(
            HOST),
        additional_env=env_vars )
    ctx.instance.runtime_properties['install_output'] = output
