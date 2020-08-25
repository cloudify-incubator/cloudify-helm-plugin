import os
import sys
import shutil
import zipfile
import tarfile
import tempfile

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError
from cloudify.utils import exception_to_error_cause

from helm_sdk.utils import run_subprocess
from decorators import skip_if_existing, with_helm
from utils import is_using_existing, get_helm_local_files_dirs
from constants import FLAGS_FIELD


@operation
def install(ctx, **_):
    def _untar_and_set_permissions(tar_file, target_dir):
        ctx.logger.info("Untarring into %s", target_dir)
        with tarfile.open(tar_file, 'r') as tar_ref:
            for name in tar_ref.getnames():
                if 'helm' in name:
                    tar_ref.extract(name, target_dir)
                    target_file = os.path.join(target_dir, name)
                    ctx.logger.info("Setting permission on %s",
                                    target_file)
                    run_subprocess(
                        ['chmod', 'u+x', target_file],
                        ctx.logger
                    )

    def find_binary_and_copy(source_dir, target_dir):
        for root, dir, f in os.walk(source_dir):
            for file in f:
                if file.endswith('helm'):
                    print "moving{0} to {1}".format(os.path.join(root, file),
                                                    target_dir)
                    if not os.path.isdir(target_dir):
                        os.makedirs(target_dir)
                    shutil.move(os.path.join(root, file), target_dir)

    executable_path = ctx.node.properties.get(
        'helm_config', {}).get('executable_path', "")
    installation_temp_dir = tempfile.mkdtemp()
    try:
        if not is_using_existing(ctx):
            if os.path.isfile(executable_path):
                ctx.logger.info(
                    "Helm executable already found at %s; " +
                    "skipping installation of executable",
                    executable_path)
            else:
                installation_source = \
                    ctx.node.properties.get(
                        'installation_source', "")
                if not installation_source:
                    raise NonRecoverableError("invalid installation_source")
                installation_tar = \
                    os.path.join(installation_temp_dir, 'helm.tar.gz')

                ctx.logger.info("Downloading Helm from %s into %s",
                                installation_source, installation_tar)
                run_subprocess(
                    ['curl', '-o', installation_tar, installation_source],
                    ctx.logger
                )
                _untar_and_set_permissions(installation_tar,
                                           installation_temp_dir)
                executable_dir = os.path.dirname(executable_path)
                # need to find helm binary in the extracted files
                find_binary_and_copy(installation_temp_dir, executable_dir)

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
        ctx.logger.info("Removing executable: %s", executable_path)
        os.remove(executable_path)
    # helm_local_files_dirs = get_helm_local_files_dirs()
    # for dir_to_delete in helm_local_files_dirs:
    #     if os.path.isdir(dir_to_delete):
    #         ctx.logger.info("Removing: {}".format(dir_to_delete))
    #
    #         shutil.rmtree(dir_to_delete)
    #     else:
    #         ctx.logger.info("Directory %s doesn't exist; skipping",
    #                         dir_to_delete)


def _prepare_release_args(ctx, flags=None):
    """
    Prepare arguments to helm.install/helm.uninstall function.
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
    try:
        args_dict = _prepare_release_args(ctx, kwargs.get('flags'))
        output = helm.install(values_file=values_file,
                              kubeconfig=kubeconfig,
                              token=ctx.node.properties.get('client_config',
                                                            {}).get(
                                  'kube_token'),
                              apiserver=ctx.node.properties.get(
                                  'client_config', {}).get('kube_api_server'),
                              **args_dict)
        ctx.instance.runtime_properties['install_output'] = output
    except Exception as ex:
        _, _, tb = sys.exc_info()
        raise NonRecoverableError(
            "Failed installing release",
            causes=[exception_to_error_cause(ex, tb)])
