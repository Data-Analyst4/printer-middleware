def build_command(template, data):
    template_cmd = {
        "command": "STAR",
        "templatename": template,
        "startpage": "1",
        "endpage": "1",
        "loop": "false"
    }

    data_cmd = {
        "command": "DATA",
        "data": data
    }

    return [template_cmd, data_cmd]