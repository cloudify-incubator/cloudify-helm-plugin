########
# Copyright (c) 2019 - 2023 Cloudify Platform Ltd. All rights reserved
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
from deepdiff import DeepDiff

from urllib.parse import urlparse
from contextlib import contextmanager

from cloudify import ctx as ctx_from_import
from cloudify_common_sdk.utils import get_deployment_dir
from cloudify_kubernetes_sdk.connection import decorators

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from .decorators import (with_helm, with_kubernetes, prepare_aws)
from .utils import (
    get_binary,
    copy_binary,
    helm_from_ctx,
    get_release_name,
    is_using_existing,
    get_resource_config,
    convert_string_to_dict,
    get_helm_executable_path,
    use_existing_repo_on_helm,
    create_temporary_env_of_helm,
    delete_temporary_env_of_helm)
from .constants import (
    FLAGS_FIELD,
    VALUES_FILE,
    HELM_CONFIG,
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
    executable_path = get_helm_executable_path(
        ctx.node.properties, ctx.instance.runtime_properties)
    if os.path.isfile(executable_path) and not is_using_existing(ctx):
        ctx.logger.info("Removing executable: {0}".format(executable_path))
        os.remove(executable_path)
    delete_temporary_env_of_helm(ctx)


@operation
def check_status_binary(ctx, **_):
    executable_path = get_helm_executable_path(
        ctx.node.properties, ctx.instance.runtime_properties)
    if os.path.isfile(executable_path):
        return
    elif ctx.workflow_id == 'heal' and ctx.operation.retry_number == 0:
        install_binary(ctx, **_)
    raise RuntimeError('The executable file {} is missing.'.format(
        executable_path))


def prepare_args(resource_config, flags=None, max_sleep_time=None):
    """
    Prepare arguments dictionary to helm  sdk function(like:helm.install,
    helm.repo_add).
    :resource_config dict: node props.
    :param ctx: cloudify context.
    :param flags: flags that user passed - unique for install operation.
    :return arguments dictionary for helm.install function
    """
    flags = flags or []  # This could be flags input to operation.
    args_dict = {}  # This is the new args dict.
    args_dict.update(resource_config or {})
    args_dict.pop(VALUES_FILE, None)
    # Unite the flags lists and copy
    all_flags = args_dict[FLAGS_FIELD] + flags
    args_dict[FLAGS_FIELD] = []
    # de-duplicate
    for value in all_flags:
        if value in args_dict[FLAGS_FIELD]:
            continue
        args_dict[FLAGS_FIELD].append(value)
    if 'additional_args' not in args_dict:
        additional_args = {
            'max_sleep_time': max_sleep_time or 300
        }
        args_dict['additional_args'] = additional_args
    return args_dict


@contextmanager
def install_target(ctx, url, args_dict):
    ctx.logger.debug(
        "install_target with {url}".format(url=url))
    if url.path and not any([url.path.endswith('.tgz'),
                             url.path.endswith('.zip'),
                             url.path.endswith('.tar.gz')]):
        # this is a <repo>/<chart>
        yield args_dict
    elif url.path and url.scheme.startswith("http"):
        # let helm use the url
        yield args_dict
    elif url.path and '' in url.scheme:
        # use the local file as input and create the copy
        # resources/package.tgz
        source_tmp_path = ctx.download_resource(url.path)
        ctx.logger.debug('Downloaded temporary source path {}'
                         .format(source_tmp_path))
        args_dict['chart'] = source_tmp_path
        yield args_dict


@operation
@with_helm()
def add_repo(ctx, helm, **kwargs):
    if not use_existing_repo_on_helm(ctx, helm):
        resource_config = get_resource_config()
        args_dict = prepare_args(
            resource_config,
            kwargs.get(FLAGS_FIELD),
            ctx.node.properties.get('max_sleep_time')
        )
        helm.repo_add(**args_dict)
    output = helm.repo_list()
    ctx.instance.runtime_properties['list_output'] = output


@operation
@with_helm()
def registry_login(ctx, helm, **kwargs):
    resource_config = get_resource_config()
    flags = kwargs.get(FLAGS_FIELD, [])
    args_dict = prepare_args(
        resource_config,
        flags,
        ctx.node.properties.get('max_sleep_time')
    )
    helm.registry_login(**args_dict)


@operation
@with_helm()
def registry_logout(ctx, helm, **kwargs):
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    helm.registry_logout(**args_dict)


def show_chart(helm, release_name, repo_url):
    """
    Execute helm show chart CHART_NAME --repo REPO_URL
    :param helm:
    :param release_name:
    :param repo_url:
    :return:
    show the chart's definition in type string.
    For example:
    apiVersion: xx
    appVersion: x.x.x
    description: xxx
    name: helm-chart-name
    type: application
    version: x.x.x
    """
    output = helm.show_chart(release_name, repo_url)
    return convert_string_to_dict(output)


@operation
@with_helm()
def repo_list(ctx, helm, **kwargs):
    output = helm.repo_list()
    if output != ctx.instance.runtime_properties['list_output']:
        return output


@operation
@with_helm()
def repo_check_drift(ctx, helm, **kwargs):
    ctx.logger.info(
        'If you ran check status before check drift, the status is going to '
        'match the current status and no drift could be detected.')

    output = helm.repo_list()
    if 'list_output' not in ctx.instance.runtime_properties:
        ctx.instance.runtime_properties['list_output'] = output
    diff = DeepDiff(ctx.instance.runtime_properties['list_output'], output)
    if diff:
        return diff


@operation
@with_helm()
def remove_repo(ctx, helm, **kwargs):
    if not ctx.node.properties.get(USE_EXTERNAL_RESOURCE):
        resource_config = get_resource_config()
        args_dict = prepare_args(
            resource_config,
            kwargs.get(FLAGS_FIELD),
            ctx.node.properties.get('max_sleep_time')
        )
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
    ctx.instance.runtime_properties['repo_list'] = helm.repo_list()


@operation
@decorators.with_connection_details
@with_helm()
@with_kubernetes
@prepare_aws
def install_release(ctx,
                    helm,
                    kubernetes,
                    kubeconfig=None,
                    values_file=None,
                    token=None,
                    env_vars=None,
                    ca_file=None,
                    host=None,
                    **kwargs):
    """
    Execute helm install.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :param kubernetes: kubernetes client object.
    :param kubeconfig: kubeconfig path
    :param values_file: values file path
    :return output of `helm install` command
    """
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    url = urlparse(args_dict.get('chart', None))
    release_name = get_release_name(args_dict)

    with install_target(ctx, url, args_dict) as args_dict:
        if ctx.workflow_id == 'update':
            output = helm.upgrade(
                release_name,
                values_file=values_file,
                kubeconfig=kubeconfig,
                token=token,
                apiserver=host,
                additional_env=env_vars,
                ca_file=ca_file,
                **args_dict)
        else:
            output = helm.install(
                release_name,
                values_file=values_file,
                kubeconfig=kubeconfig,
                token=token,
                apiserver=host,
                additional_env=env_vars,
                ca_file=ca_file,
                **args_dict)
        ctx.instance.runtime_properties['install_output'] = output
        helm_state = helm.status(
            release_name,
            values_file=values_file,
            kubeconfig=kubeconfig,
            token=token,
            apiserver=host,
            additional_env=env_vars,
            ca_file=ca_file,
            **args_dict,
        )
        ctx.instance.runtime_properties['status_output'] = helm_state
        k8s_state = kubernetes.multiple_resource_status(helm_state)
        ctx.instance.runtime_properties['kubernetes_status'] = k8s_state


@operation
@decorators.with_connection_details
@with_helm()
@prepare_aws
def uninstall_release(ctx,
                      helm,
                      kubeconfig=None,
                      token=None,
                      env_vars=None,
                      ca_file=None,
                      host=None,
                      **kwargs):
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    if FLAGS_FIELD in args_dict:
        for n in range(0, len(args_dict[FLAGS_FIELD])):
            if args_dict[FLAGS_FIELD][n].get('name') == 'version':
                del args_dict[FLAGS_FIELD][n]
    release_name = get_release_name(args_dict)
    helm.uninstall(
        release_name,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
        **args_dict)


@operation
@decorators.with_connection_details
@with_helm(ignore_properties_values_file=True)
@with_kubernetes
@prepare_aws
def upgrade_release(ctx,
                    helm,
                    kubernetes,
                    chart='',
                    kubeconfig=None,
                    values_file=None,
                    token=None,
                    env_vars=None,
                    ca_file=None,
                    host=None,
                    **kwargs):
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
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    release_name = get_release_name(args_dict)
    output = helm.upgrade(
        release_name,
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
        **args_dict,
    )
    ctx.instance.runtime_properties['install_output'] = output
    helm_state = helm.status(
        release_name=release_name,
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
        **args_dict,
    )
    ctx.instance.runtime_properties['status_output'] = helm_state
    k8s_state = kubernetes.multiple_resource_status(helm_state)
    ctx.instance.runtime_properties['kubernetes_status'] = k8s_state


@operation
@decorators.with_connection_details
@with_helm(ignore_properties_values_file=True)
@with_kubernetes
@prepare_aws
def check_release_status(ctx,
                         helm,
                         kubernetes,
                         kubeconfig=None,
                         values_file=None,
                         token=None,
                         flags=None,
                         env_vars=None,
                         ca_file=None,
                         host=None,
                         **kwargs):
    """
    Execute helm status.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :param kubeconfig: kubeconfig path.
    :return output of `helm upgrade` command
    """

    ctx.logger.debug(
        "Checking if used local packaged chart file, If local file used and "
        "the command failed check file access permissions.")
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        flags,
        ctx.node.properties.get('max_sleep_time')
    )

    release_name = get_release_name(args_dict)
    helm_state = helm.status(
        release_name=release_name,
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
        **args_dict,
    )

    get_status(ctx.instance, helm_state)
    if not 'deployed' == helm_state['info']['status']:
        raise RuntimeError(
            'Unexpected Helm Status. Expected "deployed", '
            'received: {}'.format(helm_state['info']['status']))

    status, errors = kubernetes.multiple_resource_check_status(helm_state)
    ctx.logger.info('Status: {}'.format(status))
    ctx.logger.info('Errors: {}'.format(errors))
    if errors and ctx.workflow_id == 'install':
        return
    elif errors and ctx.workflow_id == 'heal' \
            and ctx.operation.retry_number == 0 \
            and 'check_status' in ctx.operation.name:
        helm.upgrade(
            release_name,
            values_file=values_file,
            kubeconfig=kubeconfig,
            token=token,
            apiserver=host,
            additional_env=env_vars,
            ca_file=ca_file,
            **args_dict,
        )
        return ctx.operation.retry('Attempting to heal release...')
    elif errors:
        return errors


@operation
@decorators.with_connection_details
@with_helm(ignore_properties_values_file=True)
@with_kubernetes
@prepare_aws
def check_release_drift(ctx,
                        helm,
                        kubernetes,
                        kubeconfig=None,
                        values_file=None,
                        token=None,
                        flags=None,
                        env_vars=None,
                        ca_file=None,
                        host=None,
                        **_):
    """
    Execute helm release Drift.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :param kubernetes: kubernetes client object.
    :param kubeconfig: kubeconfig path.
    :return output of `helm upgrade` command
    """
    ctx.logger.info(
        'If you ran check status before check drift, the status is going to '
        'match the current status and no drift could be detected.')
    ctx.logger.debug(
        "Checking if used local packaged chart file, If local file used and "
        "the command failed check file access permissions.")
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        flags,
        ctx.node.properties.get('max_sleep_time')
    )
    release_name = get_release_name(args_dict)
    helm_state = helm.status(
        release_name=release_name,
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
        **args_dict,
    )
    diff = get_diff(ctx.instance,
                    kubernetes.multiple_resource_status(helm_state))
    if diff:
        return diff


def get_status(ctx_instance, helm_status):
    return DeepDiff(
        ctx_instance.runtime_properties['status_output'], helm_status)


def get_diff(ctx_instance, kube_status):
    return DeepDiff(
        ctx_instance.runtime_properties['kubernetes_status'], kube_status)


@operation
@with_helm()
def pull_chart(ctx, helm, **kwargs):
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    url = urlparse(args_dict.get('chart', None))
    with install_target(ctx, url, args_dict) as args_dict:
        if 'name' in args_dict:
            del args_dict['name']
        if 'set_values' in args_dict:
            del args_dict['set_values']
        helm.pull(**args_dict)


@operation
@with_helm()
def push_chart(ctx, helm, **kwargs):
    resource_config = get_resource_config()
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    url = urlparse(args_dict.get('chart', None))
    with install_target(ctx, url, args_dict) as args_dict:
        if 'name' in args_dict:
            del args_dict['name']
        if 'set_values' in args_dict:
            del args_dict['set_values']
        helm.push(**args_dict)
