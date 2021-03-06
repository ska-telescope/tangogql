import json


# TODO: required_groups should be renamed in order not to make clear that:
# - only one group needs to match
# - an empty list means no restrictions (does this make sense?)


class Config:
    def __init__(self, file):
        data = json.load(file)

        try:
            secret = data["secret"]
        except KeyError:
            raise ConfigError("no secret provided")

        if not isinstance(secret, str):
            raise ConfigError("secret must be a string")

        required_groups = data.get("required_groups", [])
        if not all(isinstance(group, str) for group in required_groups):
            raise ConfigError("required_groups must consist of strings")

        self.secret = secret
        self.required_groups = required_groups


class ConfigError(Exception):
    def __init__(self, reason):
        super().__init__(f"Config error: {reason}")
