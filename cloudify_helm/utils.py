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
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from subprocess import SubprocessError

import yaml

from cloudify import ctx
from cloudify.exceptions import NonRecoverableError
from cloudify_common_sdk.utils import get_deployment_dir

from helm_sdk import Helm
from helm_sdk.utils import run_subprocess
from .configuration import KubeConfigConfigurationVariants
from .authentication import KubernetesApiAuthenticationVariants
from .constants import (
    API_KEY,
    API_OPTIONS,
    HELM_CONFIG,
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


def get_helm_executable_path(properties, runtime_properties):
    # Look for executable path in runtime property or in default place.
    return runtime_properties.get(EXECUTABLE_PATH, "") or \
           properties.get(HELM_CONFIG, {}).get(EXECUTABLE_PATH, "")


def helm_from_ctx(ctx):
    executable_path = get_helm_executable_path(ctx.node.properties,
                                               ctx.instance.runtime_properties)
    if not os.path.exists(executable_path):
        raise NonRecoverableError(
            "Helm's executable not found in {0}. Please set the "
            "'executable_path' property accordingly.".format(
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
        env_var_value = ctx.instance.runtime_properties.get(property_name, "")
        if not env_var_value:
            raise NonRecoverableError(
                "ctx of node {node_id} must have helm env variables {name}!, "
                "use run_on_host relationship.".format(
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
    values_file = values_file if ignore_properties_values_file else \
        ctx.node.properties.get(RESOURCE_CONFIG, {}).get('values_file')
    ctx.logger.debug("values file path:{path}".format(path=values_file))
    if values_file and not ignore_properties_values_file:
        # It means we took values file path from resource_config
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.close()
            ctx.download_resource(
                values_file,
                target_path=f.name)
            try:
                ctx.logger.info("using values file:{file}".format(file=f.name))
                yield f.name
            finally:
                os.remove(f.name)
    elif values_file:
        # It means we have local values file.Check if cfyuser can access it.
        if not os.path.isfile(values_file):
            raise NonRecoverableError(
                "Used local values file path but Cloudify user can`t locate "
                "it, please check file permissions.")
        yield values_file
    else:
        yield


@contextmanager
def get_binary(ctx):
    installation_temp_dir = tempfile.mkdtemp()
    installation_source = \
        ctx.node.properties.get(
            'installation_source', "")
    if not installation_source:
        raise NonRecoverableError(
            "invalid installation_source")
    installation_tar = \
        os.path.join(installation_temp_dir, 'helm.tar.gz')

    ctx.logger.info(
        "Downloading Helm from {0} into {1}".format(
            installation_source, installation_tar))
    run_subprocess(
        ['curl', '-o', installation_tar, installation_source],
        ctx.logger
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
    ctx.logger.info("Untarring into {0}".format(target_dir))
    with tarfile.open(tar_file, 'r') as tar_ref:
        for name in tar_ref.getnames():
            tar_ref.extract(name, target_dir)
            target_file = os.path.join(target_dir, name)
            ctx.logger.info(
                "Setting permission on {0}".format(target_file))
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
            "failed to copy binary: {}".format(e))


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
        resource_config = ctx.node.properties.get(RESOURCE_CONFIG, {})
        for repo in repos_list:
            if repo.get('name') == resource_config.get('name') and \
                    repo.get('url') == resource_config.get('repo_url'):
                return True
        raise NonRecoverableError(
            "cant find repository:{0} with url: {1} on helm client!".format(
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
            dir_property_name, "")
        if os.path.isdir(dir_to_delete):
            ctx.logger.info("Removing: {dir}".format(dir=dir_to_delete))
            shutil.rmtree(dir_to_delete)
        else:
            ctx.logger.info(
                "Directory {dir} doesn't exist,skipping".format(
                    dir=dir_to_delete))


def get_auth_token(ctx):
    authentication_property = ctx.node.properties.get(CLIENT_CONFIG, {}).get(
        AUTHENTICATION, {})
    token = KubernetesApiAuthenticationVariants(
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
        kubeconfig_dict = yaml.load(kube_file)
    ctx.logger.debug("Trying to get users from kubeconfig")
    users = kubeconfig_dict.get('users', {})
    for user in users:
        command = user.get('user', {}).get('exec', {}).get('command', None)
        if command == 'aws':
            return True
        if command == 'aws-iam-authenticator':
            ctx.logger.warning("Found kubeconfig user that uses "
                               "aws-iam-authenticator command,if its the user "
                               "of the current kubernetes context please use "
                               "aws command See https://docs.aws.amazon.com/"
                               "eks/latest/userguide/create-kubeconfig.html#"
                               "create-kubeconfig-manually ")
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
    ctx.logger.debug("Creating virtualenv at: {path}".format(path=path))
    run_subprocess(
        [sys.executable, '-m', 'virtualenv', path],
        ctx.logger
    )


def install_packages_to_venv(venv, packages_list):
    # Force reinstall inside venv in order to make sure
    # packages being installed on specified environment .
    if packages_list:
        ctx.logger.debug("venv = {path}".format(path=venv))
        command = [get_executable_path('pip', venv=venv), 'install',
                   '--force-reinstall', '--retries=2',
                   '--timeout=15'] + packages_list
        ctx.logger.debug("cmd:{command}".format(command=command))
        ctx.logger.info("Installing {packages} inside venv: {venv}.".format(
            packages=packages_list,
            venv=venv))
        try:
            run_subprocess(
                command=command,
                logger=ctx.logger,
                cwd=venv,
                additional_env={'PYTHONPATH': ''})

        except SubprocessError as e:
            raise NonRecoverableError("Failed install packages: {packages}"
                                      " inside venv: {venv}. Error message: "
                                      "{err}".format(packages=packages_list,
                                                     venv=venv,
                                                     err=e))


def get_executable_path(executable, venv):
    """
    :param executable: the name of the executable
    :param venv: the venv to look for the executable in.
    """
    return '{0}/bin/{1}'.format(venv, executable) if venv else executable
