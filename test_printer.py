def test_print(ip, port):
    # Step 1: Template
    template_cmd = {
        "command": "STAR",
        "templatename": "DEMO",
        "startpage": "1",
        "endpage": "1",
        "loop": "false"
    }

    send_printer_command(ip, port, template_cmd)

    time.sleep(0.5)

    # Step 2: Data
    data_cmd = {
        "command": "DATA",
        "data": {
            "POD1": "123",
            "POD2": "456"
        }
    }

    send_printer_command(ip, port, data_cmd)