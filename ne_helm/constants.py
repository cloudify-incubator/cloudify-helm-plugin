# Copyright © 2024 Dell Inc. or its subsidiaries. All Rights Reserved.

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
