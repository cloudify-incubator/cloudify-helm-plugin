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
import sys
import yaml
import shutil
import tarfile
import tempfile
from packaging import version
from contextlib import contextmanager
from subprocess import CalledProcessError

from cloudify import ctx
from cloudify.exceptions import NonRecoverableError, HttpException
from cloudify_common_sdk.resource_downloader import (unzip_archive,
                                                     untar_archive,
                                                     TAR_FILE_EXTENSTIONS)

from cloudify_common_sdk.utils import get_ctx_instance, get_deployment_dir
from cloudify_common_sdk.secure_property_management import get_stored_property

from helm_sdk import Helm
from helm_sdk.utils import run_subprocess
from .configuration import KubeConfigConfigurationVariants
from .authentication import KubernetesApiAuthenticationVariants
from .constants import (
    HOST,
    API_KEY,
    API_OPTIONS,
    HELM_CONFIG,
    SSL_CA_CERT,
    AWS_CLI_VENV,
    CONFIGURATION,
    CLIENT_CONFIG,
    AUTHENTICATION,
    EXECUTABLE_PATH,
    RESOURCE_CONFIG,
    AWS_ENV_VAR_LIST,
    DATA_DIR_ENV_VAR,
    CACHE_DIR_ENV_VAR,
    CONFIG_DIR_ENV_VAR,
    HELM_ENV_VARS_LIST,
    AWS_CLI_TO_INSTALL,
    USE_EXTERNAL_RESOURCE)

CLUSTER_TYPE = 'cloudify.kubernetes.resources.SharedCluster'
CLUSTER_REL = 'cloudify.relationships.helm.connected_to_shared_cluster'


def get_resource_config(target=False, force=None):
    """Get the cloudify.nodes.terraform.Module resource_config"""
    return get_stored_property(ctx, RESOURCE_CONFIG, target, force)


def create_source_path(source_tmp_path):
    # didn't download anything so check the provided path
    # if file and absolute path or not
    if not os.path.isabs(source_tmp_path):
        # bundled and need to be downloaded from blueprint
        source_tmp_path = ctx.download_resource(source_tmp_path)

    if os.path.isfile(source_tmp_path):
        file_name = source_tmp_path.rsplit('/', 1)[1]
        file_type = file_name.rsplit('.', 1)[1]
        # check type
        if file_type == 'zip':
            unzipped_source = unzip_archive(source_tmp_path, False)
            os.remove(source_tmp_path)
            source_tmp_path = unzipped_source
        elif file_type in TAR_FILE_EXTENSTIONS:
            unzipped_source = untar_archive(source_tmp_path, False)
            os.remove(source_tmp_path)
            source_tmp_path = unzipped_source
    return source_tmp_path


def get_helm_executable_path(properties, runtime_properties):
    # Look for executable path in runtime property or in default place.
    return runtime_properties.get(EXECUTABLE_PATH, '') or \
           properties.get(HELM_CONFIG, {}).get(EXECUTABLE_PATH, '')


def helm_from_ctx(ctx):
    executable_path = get_helm_executable_path(ctx.node.properties,
                                               ctx.instance.runtime_properties)
    if not os.path.exists(executable_path):
        raise NonRecoverableError(
            'Helm\'s executable not found in {0}. Please set the '
            '\'executable_path\' property accordingly.'.format(
                executable_path))
    env_variables = get_helm_env_vars_dict(ctx)
    helm = Helm(
        ctx.logger,
        executable_path,
        environment_variables=env_variables)
    return helm


def get_helm_env_vars_dict(ctx):
    env_vars = {}
    for property_name in HELM_ENV_VARS_LIST:
        env_var_value = ctx.instance.runtime_properties.get(property_name, '')
        if not env_var_value:
            raise NonRecoverableError(
                'ctx of node {node_id} must have helm env variables {name}!, '
                'use run_on_host relationship.'.format(
                    node_id=ctx.node.id, name=property_name))
        env_vars[property_name] = ctx.instance.runtime_properties.get(
            property_name)
    return env_vars


def is_using_existing(ctx):
    return ctx.node.properties.get(
        'use_existing_resource', True)


@contextmanager
def get_kubeconfig_file(ctx):
    """
    This is contextmanager that responsible to handle kubeconfig file
    resource.
    :return Path of temporary file with kubeconfig, otherwise None.
    """
    configuration_property = ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        CONFIGURATION, {})

    kubeconfig_file = KubeConfigConfigurationVariants(
        ctx.logger,
        configuration_property,
        download_resource=ctx.download_resource).get_kubeconfig()
    try:
        yield kubeconfig_file
    finally:
        if kubeconfig_file is not None:
            os.remove(kubeconfig_file)


@contextmanager
def get_values_file(ctx, ignore_properties_values_file, values_file=None):

    if ignore_properties_values_file:
        values_file = values_file
    else:
        resource_config = get_resource_config()
        values_file = resource_config.get('values_file')

    ctx.logger.debug('values file path:{path}'.format(path=values_file))
    if values_file and not ignore_properties_values_file:
        # It means we took values file path from resource_config
        with tempfile.NamedTemporaryFile(delete=False, suffix='.yaml') as f:
            f.close()
            ctx.download_resource(
                values_file,
                target_path=f.name)
            try:
                ctx.logger.info('using values file:{file}'.format(file=f.name))
                yield f.name
            finally:
                os.remove(f.name)
    elif values_file:
        # It means we have local values file.Check if cfyuser can access it.
        if not os.path.isfile(values_file):
            raise NonRecoverableError(
                'Used local values file path but Cloudify user can\'t locate '
                'it, please check file permissions.')
        yield values_file
    else:
        yield


@contextmanager
def get_ssl_ca_file(ca_from_shared_cluster=None):
    configuration_property = ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        CONFIGURATION, {})
    current_value = ca_from_shared_cluster or configuration_property.get(
        API_OPTIONS, {}).get(SSL_CA_CERT)

    if current_value and check_if_resource_inside_blueprint_folder(
            current_value):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.close()
            ctx.download_resource(
                current_value,
                target_path=f.name)
            try:
                ctx.logger.info(
                    'using CA file:{file}'.format(file=f.name))
                yield f.name
            finally:
                os.remove(f.name)

    elif current_value and os.path.isfile(current_value):
        ctx.logger.info('using CA file located at: {path}'.format(
            path=current_value))
        yield current_value

    elif current_value and not os.path.isfile(current_value):
        # It means we have the ca as a string in the blueprint
        f = tempfile.NamedTemporaryFile('w',
                                        suffix='__cfy.helm.k8s__',
                                        delete=False)
        f.write(current_value)
        f.close()
        try:
            ctx.logger.info('using CA content from the blueprint.')
            yield f.name
        finally:
            os.remove(f.name)
    else:
        ctx.logger.info('CA file not found.')
        yield


def get_cluster_node_instance_from_rels(rels, rel_type=None, node_type=None):

    rel_type = rel_type or CLUSTER_REL
    node_type = node_type or CLUSTER_TYPE
    for x in rels:
        if rel_type in x.type_hierarchy and \
                node_type in x.target.node.type_hierarchy:
            return x


def get_connection_details_from_shared_cluster(props):
    node_instance = get_ctx_instance(ctx)
    x = get_cluster_node_instance_from_rels(node_instance.relationships)
    if not x:
        return props.get(CLIENT_CONFIG, {}).get(CONFIGURATION, {}).get(
            API_OPTIONS, {}).get(HOST),\
               props.get(CLIENT_CONFIG, {}).get(CONFIGURATION, {}).get(
                   API_OPTIONS, {}).get('api_key'),\
               props.get(CLIENT_CONFIG, {}).get(CONFIGURATION, {}).get(
                   API_OPTIONS, {}).get('ssl_ca_cert')
    endpoint = x.target.instance.runtime_properties['k8s-ip']
    token = x.target.instance.runtime_properties['k8s-service-account-token']
    ssl_ca_cert = x.target.instance.runtime_properties['k8s-cacert']
    return endpoint, token, ssl_ca_cert


def check_if_resource_inside_blueprint_folder(path):
    with tempfile.NamedTemporaryFile(delete=True) as f:
        f.close()
        try:
            ctx.download_resource(
                path,
                target_path=f.name)
            return True
        except HttpException:
            ctx.logger.debug('ssl_ca file not found inside blueprint package.')
            return False


@contextmanager
def get_binary(ctx):
    installation_temp_dir = tempfile.mkdtemp()
    installation_source = \
        ctx.node.properties.get(
            'installation_source', '')
    if not installation_source:
        raise NonRecoverableError(
            'invalid installation_source')
    installation_tar = \
        os.path.join(installation_temp_dir, 'helm.tar.gz')

    ctx.logger.info('ctx.node.properties: {0}'.format(ctx.node.properties))

    additional_args = {
        'max_sleep_time': ctx.node.properties.get('max_sleep_time')
    }
    ctx.logger.info(
        'Downloading Helm from {0} into {1}'.format(
            installation_source, installation_tar))
    run_subprocess(
        ['curl', '-o', installation_tar, installation_source],
        ctx.logger,
        additional_args=additional_args
    )
    untar_and_set_permissions(ctx,
                              installation_tar,
                              installation_temp_dir)
    # Need to find helm binary in the extracted files
    binary = find_binary(installation_temp_dir)
    try:
        yield binary
    finally:
        shutil.rmtree(installation_temp_dir)


def untar_and_set_permissions(ctx, tar_file, target_dir):
    ctx.logger.info('Untarring into {0}'.format(target_dir))
    with tarfile.open(tar_file, 'r') as tar_ref:
        for name in tar_ref.getnames():
            tar_ref.extract(name, target_dir)
            target_file = os.path.join(target_dir, name)
            ctx.logger.info(
                'Setting permission on {0}'.format(target_file))
            run_subprocess(
                ['chmod', 'u+x', target_file],
                ctx.logger
            )


def find_binary(source_dir):
    for root, dir, filenames in os.walk(source_dir):
        for file in filenames:
            if file.endswith('helm'):
                return os.path.join(root, file)


def copy_binary(source, dest):
    if not os.path.isdir(os.path.dirname(dest)):
        os.makedirs(os.path.dirname(dest))
    try:
        shutil.copy2(source, dest)
    except Exception as e:
        raise NonRecoverableError(
            'failed to copy binary: {}'.format(e))


def use_existing_repo_on_helm(ctx, helm):
    """
    Check if a repo that user asked for in resource_config exists on helm
    client.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :return Nothing, raises NonRecoverableError exception if repository
    doesen't exist.
    """
    if ctx.node.properties.get(USE_EXTERNAL_RESOURCE):
        repos_list = helm.repo_list()
        resource_config = get_resource_config()
        for repo in repos_list:
            if repo.get('name') == resource_config.get('name') and \
                    repo.get('url') == resource_config.get('repo_url'):
                return True
        raise NonRecoverableError(
            'cant find repository:{0} with url: {1} on helm client!'.format(
                resource_config.get('name'), resource_config.get('repo_url')))


def create_temporary_env_of_helm(ctx):
    """
    Create temporary directories for helm cache,data and configuration files
    and inject their paths to runtime properties.
    :param ctx: cloudify context.

    """
    deployment_dir = get_deployment_dir(ctx.deployment.id)
    ctx.instance.runtime_properties[CACHE_DIR_ENV_VAR] = tempfile.mkdtemp(
        dir=deployment_dir)
    ctx.instance.runtime_properties[CONFIG_DIR_ENV_VAR] = tempfile.mkdtemp(
        dir=deployment_dir)
    ctx.instance.runtime_properties[DATA_DIR_ENV_VAR] = tempfile.mkdtemp(
        dir=deployment_dir)


def delete_temporary_env_of_helm(ctx):
    for dir_property_name in HELM_ENV_VARS_LIST:
        dir_to_delete = ctx.instance.runtime_properties.get(
            dir_property_name, '')
        if os.path.isdir(dir_to_delete):
            ctx.logger.info('Removing: {dir}'.format(dir=dir_to_delete))
            shutil.rmtree(dir_to_delete)
        else:
            ctx.logger.info(
                'Directory {dir} doesn\'t exist,skipping'.format(
                    dir=dir_to_delete))


def get_auth_token(ctx, token_from_shared_cluster):
    authentication_property = ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        AUTHENTICATION, {})
    token = token_from_shared_cluster or KubernetesApiAuthenticationVariants(
        ctx.logger,
        authentication_property,
    ).get_token()
    # If the user specify token so its in higher priority.
    return ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        CONFIGURATION, {}).get(API_OPTIONS, {}).get(API_KEY) or token


def prepare_aws_env(kubeconfig):
    """
    Install aws cli if needed.
    If the cli installed, return aws credentials dictionary to append to helm
    command invocation.
    :param kubeconfig: kubeconfig path
    """
    install_aws_cli_if_needed(kubeconfig)
    return prepare_aws_env_vars_dict()


def prepare_aws_env_vars_dict():
    """
    Create aws env vras dictionary for aws cli invocation.
    If AWS_CLI_VENV runtime property exist, all aws credentials exists under
    client_config.authentication
    """
    aws_env_dict = {}
    aws_cli_venv = ctx.instance.runtime_properties.get(AWS_CLI_VENV)
    if not aws_cli_venv:
        return aws_env_dict
    # Add virtual environment to path in order to use aws cli.
    aws_env_dict['PATH'] = aws_cli_venv + '/bin:' + os.environ.get('PATH')
    authentication_property = ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        AUTHENTICATION, {})
    for aws_env_var in AWS_ENV_VAR_LIST:
        aws_env_dict[aws_env_var] = authentication_property.get(
            aws_env_var.lower())
    return aws_env_dict


def install_aws_cli_if_needed(kubeconfig=None):
    """
    Install AWS cli inside virtual environment to support native use of
    authentication for aws.
    :param kubeconfig: kubeconfig path
    """
    if not kubeconfig or not check_aws_cmd_in_kubeconfig(kubeconfig):
        return
    authentication_property = ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        AUTHENTICATION, {})
    for aws_env_var in AWS_ENV_VAR_LIST:
        if not authentication_property.get(aws_env_var.lower()):
            raise NonRecoverableError('Found that aws cli needed in order to'
                                      ' authenticate with kubernetes, but one '
                                      'of: aws_access_key_id, '
                                      'aws_secret_access_key, '
                                      'aws_default_region is missing under '
                                      'client_config.authentication ')
    create_venv()


def check_aws_cmd_in_kubeconfig(kubeconfig):
    with open(kubeconfig) as kube_file:
        kubeconfig_dict = yaml.safe_load(kube_file)
    users = kubeconfig_dict.get('users', {})
    for user in users:
        command = user.get('user', {}).get('exec', {}).get('command', None)
        if command == 'aws':
            return True
        if command == 'aws-iam-authenticator':
            ctx.logger.warning('Found kubeconfig user that uses '
                               'aws-iam-authenticator command,if its the user '
                               'of the current kubernetes context please use '
                               'aws command See https://docs.aws.amazon.com/'
                               'eks/latest/userguide/create-kubeconfig.html#'
                               'create-kubeconfig-manually ')
    return False


def create_venv():
    """
        Handle creation of virtual environment.
        Create the virtual environment in deployment directory.
        Save the path of the virtual environment in runtime properties.
       :param packages_to_install: list of python packages to install
        inside venv.
    """
    if not ctx.instance.runtime_properties.get(AWS_CLI_VENV):
        deployment_dir = get_deployment_dir(ctx.deployment.id)
        venv_path = tempfile.mkdtemp(dir=deployment_dir)
        make_virtualenv(path=venv_path)
        install_packages_to_venv(venv_path, [AWS_CLI_TO_INSTALL])
        ctx.instance.runtime_properties[AWS_CLI_VENV] = venv_path


def make_virtualenv(path):
    """
        Make a venv for installing aws cli inside.
    """
    ctx.logger.debug('Creating virtualenv at: {path}'.format(path=path))
    additional_args = {
        'max_sleep_time': ctx.node.properties.get('max_sleep_time')
    }
    run_subprocess(
        [sys.executable, '-m', 'virtualenv', path],
        ctx.logger,
        additional_args=additional_args
    )


def install_packages_to_venv(venv, packages_list):
    # Force reinstall inside venv in order to make sure
    # packages being installed on specified environment .
    if packages_list:
        ctx.logger.debug('venv = {path}'.format(path=venv))
        command = [get_executable_path('pip', venv=venv), 'install',
                   '--force-reinstall', '--retries=2',
                   '--timeout=15'] + packages_list
        ctx.logger.debug('cmd:{command}'.format(command=command))
        ctx.logger.info('Installing {packages} inside venv: {venv}.'.format(
            packages=packages_list,
            venv=venv))
        additional_args = {
            'max_sleep_time': ctx.node.properties.get('max_sleep_time')
        }
        try:
            run_subprocess(
                command=command,
                logger=ctx.logger,
                cwd=venv,
                additional_env={'PYTHONPATH': ''},
                additional_args=additional_args)

        except CalledProcessError as e:
            raise NonRecoverableError('Failed install packages: {packages}'
                                      ' inside venv: {venv}. Error message: '
                                      '{err}'.format(packages=packages_list,
                                                     venv=venv,
                                                     err=e))


def get_executable_path(executable, venv):
    """
    :param executable: the name of the executable
    :param venv: the venv to look for the executable in.
    """
    return '{0}/bin/{1}'.format(venv, executable) if venv else executable


def get_release_name(args_dict):
    release_name = None
    if 'name' in args_dict:
        release_name = args_dict.pop('name')
    if 'release_name' in args_dict:
        release_name = args_dict.pop('release_name')
    if not release_name:
        raise NonRecoverableError(
            'The parameters "name" or "release_name" was not provided.')
    return release_name


def v1_equal_v2(v1, v2):
    return version.parse(str(v1)) == version.parse(str(v2))


def v1_bigger_v2(v1, v2):
    return version.parse(str(v1)) > version.parse(str(v2))


def find_rels_by_node_type(node_instance, node_type):
    return [x for x in node_instance.relationships
            if node_type in x.target.node.type_hierarchy]


def convert_string_to_dict(txt):
    """
    :param txt: string type
    :return: dict
    """
    output = {}
    rows = txt.split('\n')
    for row in rows:
        words = row.split(':')
        # Make sure it's not empty like ['']
        if len(words) == 2:
            output[words[0]] = words[1]
    return output


def find_repo_nodes():
    rels = find_rels_by_node_type(ctx.instance, 'cloudify.nodes.helm.Repo')
    nodes = []
    for rel in rels:
        nodes.append(rel.target.node)
    if not nodes:
        raise NonRecoverableError("Failed to run check_release_drift "
                                  "because it did not find "
                                  "'cloudify.nodes.helm.Repo'.")
    return nodes


def get_repo_resource_config(release_name):
    for node in find_repo_nodes():
        if 'resource_config' in node.properties and \
                node.properties['resource_config'].get('name', None) == \
                release_name:
            return node.properties['resource_config']
