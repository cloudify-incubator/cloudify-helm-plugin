import os
import sys
import shutil
import tarfile
import tempfile

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from helm_sdk.utils import run_subprocess
from .decorators import skip_if_existing, with_helm
from .constants import (
    FLAGS_FIELD,
    USE_EXTERNAL_RESOURCE)
from .utils import (
    is_using_existing,
    find_binary_and_copy,
    get_helm_local_files_dirs,
    untar_and_set_permissions,
    check_if_repo_exists_on_helm)


@operation
@skip_if_existing
def install(ctx, **_):
    executable_path = ctx.node.properties.get(
        'helm_config', {}).get('executable_path', "")
    installation_temp_dir = tempfile.mkdtemp()
    try:
        if not is_using_existing(ctx):
            if os.path.isfile(executable_path):
                ctx.logger.info(
                    "Helm executable already found at {0}; " +
                    "skipping installation of executable".format(
                        executable_path))
            else:
                installation_source = \
                    ctx.node.properties.get(
                        'installation_source', "")
                if not installation_source:
                    raise NonRecoverableError("invalid installation_source")
                installation_tar = \
                    os.path.join(installation_temp_dir, 'helm.tar.gz')

                ctx.logger.info("Downloading Helm from {0} into {1}".format(
                    installation_source, installation_tar))
                run_subprocess(
                    ['curl', '-o', installation_tar, installation_source],
                    ctx.logger
                )
                untar_and_set_permissions(ctx, installation_tar,
                                          installation_temp_dir)
                # Need to find helm binary in the extracted files
                find_binary_and_copy(installation_temp_dir, executable_path)

        ctx.instance.runtime_properties['executable_path'] = executable_path
    finally:
        if installation_temp_dir:
            shutil.rmtree(installation_temp_dir)


@operation
@skip_if_existing
def uninstall(ctx, **_):
    executable_path = ctx.node.properties.get('helm_config', {}).get(
        'executable_path', "")
    if os.path.isfile(executable_path):
        ctx.logger.info("Removing executable: {0}".format(executable_path))
        os.remove(executable_path)
    # helm_local_files_dirs = get_helm_local_files_dirs()
    # for dir_to_delete in helm_local_files_dirs:
    #     if os.path.isdir(dir_to_delete):
    #         ctx.logger.info("Removing: {}".format(dir_to_delete))
    #
    #         shutil.rmtree(dir_to_delete)
    #     else:
    #         ctx.logger.info("Directory {0} doesn't exist;
    #         skipping".format(dir_to_delete))
    #


def prepare_args(ctx, flags=None):
    """
    Prepare arguments dictionary to helm  sdk function(like:helm.install,
    helm.repo_add).
    :param ctx: cloudify context.
    :param flags: flags that user passed -unique for install operation.
    :return arguments dictionary for helm.install function
    """
    flags = flags or []
    args_dict = {}
    args_dict.update(ctx.node.properties.get('resource_config', {}))
    args_dict[FLAGS_FIELD] = args_dict[FLAGS_FIELD] + flags
    return args_dict


@operation
@with_helm
def install_release(ctx, helm, kubeconfig=None, values_file=None, **kwargs):
    """
    Execute helm install.
    :param ctx: cloudify context.
    :param helm: helm client object.
    :param kubeconfig: kubeconfig path
    :param values_file: values file path
    :return output of `helm install` command
    """
    args_dict = prepare_args(ctx, kwargs.get('flags'))
    output = helm.install(
        values_file=values_file,
        kubeconfig=kubeconfig,
        token=ctx.node.properties.get('client_config', {}).get(
            'kube_token'),
        apiserver=ctx.node.properties.get(
            'client_config', {}).get('kube_api_server'), **args_dict)
    ctx.instance.runtime_properties['install_output'] = output


@operation
@with_helm
def add_repo(ctx, helm, **kwargs):
    if ctx.node.properties.get(USE_EXTERNAL_RESOURCE):
        check_if_repo_exists_on_helm(ctx, helm)
    else:
        args_dict = prepare_args(ctx, kwargs.get('flags'))
        helm.repo_add(**args_dict)


@operation
@with_helm
def remove_repo(ctx, helm, **kwargs):
    if ctx.node.properties.get(USE_EXTERNAL_RESOURCE):
        # Use external resource means we don`t want to remove it from helm.
        pass
    else:
        args_dict = prepare_args(ctx, kwargs.get('flags'))
        helm.repo_remove(**args_dict)
