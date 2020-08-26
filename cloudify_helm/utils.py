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
import shutil
import tarfile
import tempfile
from contextlib import contextmanager

from cloudify.exceptions import NonRecoverableError

from helm_sdk import Helm
from helm_sdk.utils import run_subprocess
from .constants import (HOME_DIR_ENV_VAR,
                        CONFIG_DIR_ENV_VAR,
                        CACHE_DIR_ENV_VAR,
                        DATA_DIR_ENV_VAR,
                        CLIENT_CONFIG,
                        RESOURCE_CONFIG,
                        USE_EXTERNAL_RESOURCE)


def helm_from_ctx(ctx):
    # Look for executable path in default place.
    executable_path = \
        ctx.node.properties.get('helm_config', {}).get('executable_path', "")
    if not os.path.exists(executable_path):
        raise NonRecoverableError(
            "Helm's executable not found in {0}. Please set the "
            "'executable_path' property accordingly.".format(
                executable_path))
    # For future use.
    env_variables = ctx.node.properties.get('environment_variables', {})
    helm = Helm(
        ctx.logger,
        executable_path,
        environment_variables=env_variables)
    return helm


def is_using_existing(ctx):
    return ctx.node.properties.get(
        'use_existing_resource', True)


def get_helm_local_files_dirs():
    if os.environ.get(CACHE_DIR_ENV_VAR):
        cache_path = os.path.join(os.environ.get(CACHE_DIR_ENV_VAR), 'helm')
    else:
        cache_path = os.path.join(os.environ.get(HOME_DIR_ENV_VAR), '.cache',
                                  'helm')
    if os.environ.get(CONFIG_DIR_ENV_VAR):
        config_path = os.path.join(os.environ.get(CACHE_DIR_ENV_VAR), 'helm')
    else:
        config_path = os.path.join(os.environ.get(HOME_DIR_ENV_VAR), '.config',
                                   'helm')
    if os.environ.get(DATA_DIR_ENV_VAR):
        data_path = os.path.join(os.environ.get(DATA_DIR_ENV_VAR), 'helm')
    else:
        data_path = os.path.join(os.environ.get(HOME_DIR_ENV_VAR), '.local',
                                 'share', 'helm')

    return [cache_path, config_path, data_path]


@contextmanager
def get_kubeconfig_file(ctx):
    if ctx.node.properties.get(CLIENT_CONFIG, {}).get('kube_config'):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.close()
            ctx.download_resource(
                ctx.node.properties.get(CLIENT_CONFIG).get('kube_config'),
                target_path=f.name)
            try:
                yield f.name
            finally:
                os.remove(f.name)
    else:
        yield None


@contextmanager
def get_values_file(ctx):
    if ctx.node.properties.get(RESOURCE_CONFIG,{}).get('values_file'):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.close()
            ctx.download_resource(
                ctx.node.properties.get(RESOURCE_CONFIG).get('values_file'),
                target_path=f.name)
            try:
                yield f.name
            finally:
                os.remove(f.name)
    else:
        yield None


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


def find_binary_and_copy(source_dir, executable_path):
    for root, dir, filenames in os.walk(source_dir):
        for file in filenames:
            if file.endswith('helm'):
                if not os.path.isdir(os.path.dirname(executable_path)):
                    os.makedirs(os.path.dirname(executable_path))
                try:
                    shutil.copy2(os.path.join(root, file), executable_path)
                except Exception as e:
                    raise NonRecoverableError(
                        "failed to copy binary: {}".format(e))


def check_if_use_existing_repo_on_helm(ctx, helm):
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
        resource_config = ctx.node.properties.get('resource_config', {})
        for repo in repos_list:
            if repo.get('name') == resource_config.get('name') and \
                    repo.get('url') == resource_config.get('repo_url'):
                return True
        raise NonRecoverableError(
            "cant find repository:{0} with url: {1} on helm clinet!".format(
                resource_config.get('name'), resource_config.get('repo_url')))
