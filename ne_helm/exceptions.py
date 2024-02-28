# Copyright © 2024 Dell Inc. or its subsidiaries. All Rights Reserved.

class HelmKubeconfigInitializationFailedError(Exception):
    """Generic Error for handling issues getting kubeconfig file.
    """
    pass


class HelmKuberentesAuthenticationError(Exception):
    """Generic Error for handling issues getting authentication token.
    """
    pass
