import subprocess


def run_command(command: str) -> str:
    completed = subprocess.run(
        command,
        shell=True,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    output = completed.stdout
    if completed.stderr:
        output += "\n[stderr]\n" + completed.stderr
    return output.strip()
