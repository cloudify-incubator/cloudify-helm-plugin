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
import json
import copy
from cloudify import ctx
from cloudify_common_sdk.filters import obfuscate_passwords
from cloudify_common_sdk.processes import general_executor, process_execution
from helm_sdk.exceptions import CloudifyHelmSDKError

FLAGS_LIST_TO_VALIDATE = ['kube-apiserver', 'kube-token', 'kubeconfig']
STATUS_FLAGS = ['kube-apiserver', 'kube-token', 'kubeconfig', 'burst-limit',
                'debug', 'kube-as-group', 'kube-as-user', 'kube-ca-file',
                'kube-context', 'kube-insecure-skip-tls-verify',
                'kube-tls-server-name', 'namespace', 'registry-config',
                'repository-cache', 'repository-config']


def run_subprocess(command,
                   logger,
                   cwd=None,
                   additional_env=None,
                   additional_args=None,
                   return_output=False):

    if additional_args is None:
        additional_args = {}
    if 'max_sleep_time' not in additional_args:
        additional_args['max_sleep_time'] = 299
    args_to_pass = copy.deepcopy(additional_args)
    if additional_env:
        passed_env = args_to_pass.setdefault('env', {})
        passed_env.update(os.environ)
        passed_env.update(additional_env)

    logger.info(
        "Running: command={cmd}, cwd={cwd}, additional_args={args}".format(
            cmd=obfuscate_passwords(command),
            cwd=cwd,
            args=obfuscate_passwords(args_to_pass)))

    general_executor_params = copy.deepcopy(args_to_pass)
    general_executor_params['cwd'] = cwd
    general_executor_params['log_stdout'] = return_output
    general_executor_params['log_stderr'] = True
    general_executor_params['stderr_to_stdout'] = False
    script_path = command.pop(0)
    general_executor_params['args'] = command

    return process_execution(
        general_executor,
        script_path,
        process=general_executor_params)


def prepare_parameter(arg_dict):
    """
    Prepare single parameter.
    :param arg_dict: dictionary with the name of the flag and value(optional)
    :return: "--name=value" or -"-name"
    """
    try:
        param_string = "--" + arg_dict["name"]
        return param_string + '=' + arg_dict.get("value") if arg_dict.get(
            "value") else param_string
    except KeyError:
        raise CloudifyHelmSDKError("Parameter name doesen't exist.")


def prepare_set_parameters(set_values):
    """
    Prepare set parameters for install command.
    :param set_values: list of dictionaries with the name of the variable to
    set command and its value.
    :return list like: ["--set", "name=value","--set",
    """
    set_list = []
    for set_dict in set_values:
        set_list.append('--set')
        try:
            if isinstance(set_dict["value"], (list, dict)):
                value = json.dumps(set_dict["value"])
            elif not isinstance(set_dict["value"], str):
                value = str(set_dict["value"])
            elif isinstance(set_dict["value"], str):
                value = repr(str(set_dict["value"]))
            else:
                value = set_dict["value"]
            set_list.append(set_dict["name"] + "=" + value)
        except KeyError:
            raise CloudifyHelmSDKError(
                "\"set\" parameter name or value is missing.")
    return set_list


def validate_no_collisions_between_params_and_flags(flags):
    if [flag for flag in flags if flag['name'] in FLAGS_LIST_TO_VALIDATE]:
        raise CloudifyHelmSDKError(
            'Please do not pass {flags_list} under "flags" property,'
            'each of them has a known property.'.format(
                flags_list=FLAGS_LIST_TO_VALIDATE))


def validate_flags_for_status(flags):
    for flag in list(flags):
        if flag['name'] not in STATUS_FLAGS:
            ctx.logger.error('Removing flag {} for status check. (This will'
                             ' not affect install or update.)'.format(flag))
            flags.remove(flag)
