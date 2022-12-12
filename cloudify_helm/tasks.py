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
import re
from deepdiff import DeepDiff
from packaging import version

from urllib.parse import urlparse
from contextlib import contextmanager

from cloudify_common_sdk.utils import get_deployment_dir, get_deployment

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from .decorators import with_helm, prepare_aws
from .utils import (
    get_binary,
    copy_binary,
    helm_from_ctx,
    is_using_existing,
    get_resource_config,
    get_helm_executable_path,
    use_existing_repo_on_helm,
    create_temporary_env_of_helm,
    delete_temporary_env_of_helm)
from .constants import (
    NAME_FIELD,
    FLAGS_FIELD,
    VALUES_FILE,
    HELM_CONFIG,
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


def prepare_args(resource_config, flags=None, max_sleep_time=None):
    """
    Prepare arguments dictionary to helm  sdk function(like:helm.install,
    helm.repo_add).
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


@operation
@with_helm()
@prepare_aws
def install_release(ctx,
                    helm,
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
    :param kubeconfig: kubeconfig path
    :param values_file: values file path
    :return output of `helm install` command
    """
    resource_config = get_resource_config()
    release_name = resource_config.get(NAME_FIELD)
    args_dict = prepare_args(
        resource_config,
        kwargs.get(FLAGS_FIELD),
        ctx.node.properties.get('max_sleep_time')
    )
    url = urlparse(args_dict.get('chart', None))

    with install_target(ctx, url, args_dict) as args_dict:
        output = helm.install(
            values_file=values_file,
            kubeconfig=kubeconfig,
            token=token,
            apiserver=host,
            additional_env=env_vars,
            ca_file=ca_file,
            **args_dict)
        ctx.instance.runtime_properties['install_output'] = output

    helm_list_output = helm.list(release_name,
                                 kubeconfig=kubeconfig,
                                 token=token,
                                 apiserver=host,
                                 additional_env=env_vars,
                                 ca_file=ca_file
                                 )
    ctx.instance.runtime_properties['helm_list'] = helm_list_output


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
    helm.uninstall(
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
        **args_dict)


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


@operation
def show_chart(helm, release_name, repo_url):
    output = helm.show_chart(release_name, repo_url)
    return convert_string_to_dict(output)


def convert_string_to_dict(txt):
    output = {}
    rows = txt.split('\n')
    for row in rows:
        words = row.split(':')
        if len(words) == 2:
            output[words[0]] = words[1]
    return output


@operation
@with_helm()
def repo_list(ctx, helm, **kwargs):
    output = helm.repo_list()
    ctx.instance.runtime_properties['repo_list'] = output


@operation
@with_helm()
def repo_check_drift(ctx, helm, **kwargs):
    ctx.logger.info(
        'If you ran check status before check drift, the status is going to '
        'match the current status and no drift could be detected.')
    output = helm.repo_list()
    if 'repo_list' not in ctx.instance.runtime_properties:
        ctx.instance.runtime_properties['repo_list'] = output
        return DeepDiff(output, output)
    else:
        return DeepDiff(ctx.instance.runtime_properties['repo_list'], output)


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
                    ca_file=None,
                    host=None,
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
    resource_config = get_resource_config()
    release_name = resource_config.get(NAME_FIELD)
    output = helm.upgrade(
        release_name=release_name,
        chart=chart,
        flags=flags,
        set_values=set_values,
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
    )
    ctx.instance.runtime_properties['install_output'] = output
    helm_list_output = helm.list(release_name,
                                 kubeconfig=kubeconfig,
                                 token=token,
                                 apiserver=host,
                                 additional_env=env_vars,
                                 ca_file=ca_file
                                 )
    ctx.instance.runtime_properties['helm_list'] = helm_list_output


@operation
@with_helm(ignore_properties_values_file=True)
@prepare_aws
def check_release_status(ctx,
                         helm,
                         kubeconfig=None,
                         set_values=None,
                         token=None,
                         flags=None,
                         env_vars=None,
                         ca_file=None,
                         host=None,
                         **_):
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

    release_name = ctx.node.properties.get(RESOURCE_CONFIG, {}).get(NAME_FIELD)
    output = helm.status(
        release_name=release_name,
        flags=flags,
        set_values=set_values,
        kubeconfig=kubeconfig,
        token=token,
        apiserver=host,
        additional_env=env_vars,
        ca_file=ca_file,
    )
    ctx.instance.runtime_properties['status_output'] = output

    helm_list_output = helm.list(release_name,
                                 kubeconfig=kubeconfig,
                                 token=token,
                                 apiserver=host,
                                 additional_env=env_vars,
                                 ca_file=ca_file
                                 )
    ctx.instance.runtime_properties['helm_list'] = helm_list_output


@operation
@with_helm(ignore_properties_values_file=True)
@prepare_aws
def check_release_drift(ctx,
                        helm,
                        kubeconfig=None,
                        token=None,
                        env_vars=None,
                        ca_file=None,
                        host=None,
                        **_):
    """
    Execute helm release Drift.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :return output of `helm drifted or not drifted '
    """
    # blueprint inputs
    version_blueprint = None
    input_blueprint = get_deployment_inputs(ctx)
    release_name = input_blueprint['release_name']
    # helm-chart
    chart_name = input_blueprint['chart_name']
    # helm-chart-test
    repo_url = input_blueprint['repo_url']
    # https://nelynehemia.github.io/helm-chart/
    if 'version' in input_blueprint:
        version_blueprint = input_blueprint['version']

    # runtime properties
    version_runtime_prop = None
    if 'helm_list' in ctx.instance.runtime_properties:
        # [
        #   {
        #     "name": "helm-chart",
        #     "namespace": "default",
        #     "revision": "1",
        #     "updated": "2022-12-08 14:38:49.162025 +0000 UTC",
        #     "status": "deployed",
        #     "chart": "helm-chart-test-0.1.9",
        #     "app_version": "1.16.0"
        #   }
        # ]
        for release in ctx.instance.runtime_properties['helm_list']:
            if release_name == release.get('name'):
                chart_tgz = release.get('chart')
        version_runtime_prop = re.search(r's*([\d.]+)', chart_tgz).group(1)

    # repo
    details_chart = show_chart(helm, chart_name, repo_url)
    # details_chart: {
    # 	'apiVersion': ' v2',
    # 	'appVersion': ' 1.16.0',
    # 	'description': ' A Helm chart for Kubernetes update2',
    # 	'name': ' helm-chart-test',
    # 	'type': ' application',
    # 	'version': ' 0.2.0'
    # }
    version_show_repo = details_chart.get('version')

    # list
    helm_list_output = helm.list(release_name,
                                 kubeconfig=kubeconfig,
                                 token=token,
                                 apiserver=host,
                                 additional_env=env_vars,
                                 ca_file=ca_file
                                 )
    # helm_list_output: [{
    # 	'name': 'helm-chart',
    # 	'namespace': 'default',
    # 	'revision': '1',
    # 	'updated': '2022-12-08 14:38:49.162025 +0000 UTC',
    # 	'status': 'deployed',
    # 	'chart': 'helm-chart-test-0.1.9',
    # 	'app_version': '1.16.0'
    # }]

    for release in helm_list_output:
        if release_name == release.get('name'):
            chart_name = release.get('chart')
    version_helm_list = re.search(r's*([\d.]+)', chart_name).group(1)

    ctx.logger.info('** version_runtime_prop: {}'.format(version_runtime_prop))
    ctx.logger.info('** version_show_repo: {}'.format(version_show_repo))
    ctx.logger.info('** version_helm_list: {}'.format(version_helm_list))

    # Blueprint priority
    if version_blueprint:
        if v1_begger_v2(version_runtime_prop, version_blueprint):
            return 'drifted: The version that is in runtime_properties ' \
                   'is higher than what is in Blueprint.'
        if v1_equal_v2(version_blueprint, version_helm_list):
            return 'not drifted'

    # repo > runtime_properties
    if v1_begger_v2(version_show_repo, version_runtime_prop):
        return 'drifted -> The version that is in repo is higher in helm_list.'
    # helm_list > runtime_properties
    if v1_begger_v2(version_helm_list, version_runtime_prop):
        return 'drifted -> The version that is in helm_list is higher in ' \
               'runtime_properties '
    else:
        return 'not drifted'


def v1_equal_v2(v1, v2):
    return version.parse(str(v1)) == version.parse(str(v2))


def v1_begger_v2(v1, v2):
    return version.parse(str(v1)) > version.parse(str(v2))


def get_deployment_inputs(ctx):
    deployment = get_deployment(ctx.deployment.id)
    return deployment.inputs
