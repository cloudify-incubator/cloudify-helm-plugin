import os
import tempfile
import shutil
import sys
import zipfile

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError
from cloudify.utils import exception_to_error_cause

from helm_sdk.utils import run_subprocess
from decorators import skip_if_existing, with_helm
from utils import is_using_existing, get_helm_local_files_dirs
from constants import FLAGS_FIELD


@operation
def install(ctx, **_):
    def _unzip_and_set_permissions(zip_file, target_dir):
        ctx.logger.info("Unzipping into %s", target_dir)
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            for name in zip_ref.namelist():
                zip_ref.extract(name, target_dir)
                target_file = os.path.join(target_dir, name)
                ctx.logger.info("Setting executable permission on %s",
                                target_file)
                run_subprocess(
                    ['chmod', 'u+x', target_file],
                    ctx.logger
                )

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
                installation_zip = \
                    os.path.join(installation_temp_dir, 'helm.zip')

                ctx.logger.info("Downloading Helm from %s into %s",
                                installation_source, installation_zip)
                run_subprocess(
                    ['curl', '-o', installation_zip, installation_source],
                    ctx.logger
                )
                executable_dir = os.path.dirname(executable_path)
                _unzip_and_set_permissions(installation_zip, executable_dir)

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
    helm_local_files_dirs = get_helm_local_files_dirs()
    for dir_to_delete in helm_local_files_dirs:
        if os.path.isdir(dir_to_delete):
            ctx.logger.info("Removing: {}".format(dir_to_delete))

            shutil.rmtree(dir_to_delete)
        else:
            ctx.logger.info("Directory %s doesn't exist; skipping",
                            dir_to_delete)


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
