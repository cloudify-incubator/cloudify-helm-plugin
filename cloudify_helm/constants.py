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

HOST = "host"
NAME_FIELD = "name"
API_KEY = "api_key"
FLAGS_FIELD = "flags"
SSL_CA_CERT = "ssl_ca_cert"
HELM_CONFIG = "helm_config"
API_OPTIONS = "api_options"
VALUES_FILE = "values_file"
AWS_CLI_VENV = "aws_cli_venv"
CONFIGURATION = "configuration"
CLIENT_CONFIG = "client_config"
AUTHENTICATION = "authentication"
RESOURCE_CONFIG = "resource_config"
EXECUTABLE_PATH = "executable_path"
DATA_DIR_ENV_VAR = "HELM_DATA_HOME"
CACHE_DIR_ENV_VAR = "HELM_CACHE_HOME"
AWS_CLI_TO_INSTALL = "awscli==1.19.35"
CONFIG_DIR_ENV_VAR = "HELM_CONFIG_HOME"
USE_EXTERNAL_RESOURCE = "use_external_resource"
HELM_ENV_VARS_LIST = [DATA_DIR_ENV_VAR, CACHE_DIR_ENV_VAR,
                      CONFIG_DIR_ENV_VAR]
AWS_ENV_VAR_LIST = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                    "AWS_DEFAULT_REGION"]
