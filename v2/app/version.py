VERSION = "2.0.0"
BUILD = "production"


def get_version_info():
    return {
        "version": VERSION,
        "build": BUILD,
        "name": "printer-middleware-v2",
        "api_compat": "v1 /print sync + v2 /print/data async queue",
    }
