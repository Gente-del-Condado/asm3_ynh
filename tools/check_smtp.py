#!/usr/bin/env python3
"""Check the configured SMTP authentication without sending any message."""
import argparse
import json
from pathlib import Path
import smtplib


def check(config_file):
    config = {}
    for line in Path(config_file).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    smtp = json.loads(config["smtp_server"])
    if smtp.get("sendmail"):
        raise ValueError("This check expects an SMTP configuration")
    with smtplib.SMTP(smtp["host"], smtp["port"], timeout=15) as connection:
        connection.ehlo()
        if smtp.get("usetls"):
            connection.starttls()
            connection.ehlo()
        connection.login(smtp["username"], smtp["password"])
    print("SMTP authentication OK; no email was sent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Installed ASM3 configuration, readable by the caller")
    check(parser.parse_args().config)
