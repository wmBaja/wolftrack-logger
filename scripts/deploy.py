import argparse
import subprocess
import sys
import os
import shlex
import socket
import tarfile
from pathlib import Path

DEFAULT_AP_IP = "10.42.0.1"

def print_step(msg):
    print(f"\n\033[1;34m>>> {msg}\033[0m")

def print_success(msg):
    print(f"\033[1;32m[+] {msg}\033[0m")

def print_error(msg):
    print(f"\033[1;31m[!] {msg}\033[0m")

def run_cmd(cmd, shell=False, check=True):
    try:
        subprocess.run(cmd, shell=shell, check=check)
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {e}")
        sys.exit(1)

def get_target_host(target_ssh):
    target = target_ssh.rsplit('@', 1)[-1]
    if target.startswith('[') and ']' in target:
        return target[1:target.index(']')]
    return target.split(':', 1)[0]

def get_target_user(target_ssh):
    if '@' in target_ssh:
        return target_ssh.rsplit('@', 1)[0]
    return os.getenv("USER", "pi")

def ensure_target_resolves(target_ssh):
    host = get_target_host(target_ssh)
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        print_error(f"Could not resolve host '{host}': {e}")
        if host.endswith(".local"):
            target_user = get_target_user(target_ssh)
            print(
                "If the Pi is in Wolftrack Access Point mode, connect to the "
                "Wolftrack Wi-Fi network and deploy to the Pi's AP address:\n"
                f"  python scripts/deploy.py {target_user}@{DEFAULT_AP_IP}"
            )
            print("If you want .local names to work, check mDNS/Avahi on this computer and the Pi.")
        sys.exit(1)

def create_archive(source_dir, archive_path):
    print_step(f"Creating deployment archive from {source_dir}...")
    
    # Exclude common dev/unnecessary files
    excludes = {'.git', '.gitignore', '.venv', '__pycache__', '.idea', '.vscode', 'logs', 'app_logs', 'build', archive_path.name}
    
    def tar_filter(tarinfo):
        path = Path(tarinfo.name)
        if any(part in excludes for part in path.parts):
            return None
        return tarinfo

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name, filter=tar_filter)
        
    print_success(f"Archive created: {archive_path}")

def deploy(target_ssh, is_setup):
    project_dir = Path(__file__).parent.parent.absolute()
    project_name = project_dir.name
    build_dir = Path.joinpath(project_dir, 'build')
    archive_name = f"{project_name}_deploy.tar.gz"
    archive_path = build_dir / archive_name
    remote_tmp = f"/tmp/{archive_name}"
    remote_dest = f"/home/{target_ssh.split('@')[0]}/{project_name}" if '@' in target_ssh else f"~/{project_name}"
    Path(build_dir).mkdir(exist_ok=True)

    try:
        ensure_target_resolves(target_ssh)

        # 1. Package the project
        create_archive(project_dir, archive_path)

        # 2. Transfer to Pi
        print_step(f"Transferring archive to {target_ssh}...")
        run_cmd(["scp", str(archive_path), f"{target_ssh}:{remote_tmp}"])
        print_success("Transfer complete.")

        # 3. Extract on Pi
        print_step("Extracting on target device...")
        extract_cmd = f"tar -xzf {remote_tmp} -C ~/ && rm {remote_tmp}"
        run_cmd(["ssh", target_ssh, extract_cmd])
        print_success("Extraction complete.")

        # 4. Execute Setup or Update
        if is_setup:
            print_step("Running initial setup script on Pi...")
            print("Note: This will install dependencies, setup CAN, and convert the Pi to an Access Point.")
            setup_cmd = f"cd {remote_dest} && sudo bash scripts/setup_pi.sh"
            run_cmd(["ssh", "-t", target_ssh, setup_cmd]) # -t allocates a pseudo-TTY for sudo prompts
            print_success("Setup complete! The Pi should now reboot into Access Point mode.")
        else:
            print_step("Installing/updating systemd services and restarting...")
            remote_dest_arg = shlex.quote(remote_dest)
            services = f"{project_name} wolftrack-gps"
            update_cmd = (
                f"cd {remote_dest_arg} && "
                "remote_user=$(id -un) && "
                f"sudo bash scripts/install_services.sh {remote_dest_arg} \"$remote_user\" && "
                f"sudo systemctl restart {services} && echo '' && sudo systemctl status {services} --no-pager"
            )
            run_cmd(["ssh", "-t", target_ssh, update_cmd])
            print_success(f"Update complete! {project_name} and wolftrack-gps services restarted.")

    finally:
        # Cleanup local archive
        if archive_path.exists():
            archive_path.unlink()

def main():
    parser = argparse.ArgumentParser(description="Deploy Wolftrack Logger to a Raspberry Pi")
    parser.add_argument("target", help="SSH target for the Pi (e.g., pi@10.42.0.1 or pi@raspberrypi.local)")
    parser.add_argument("--setup", action="store_true", help="Run the initial setup script on the Pi after transfer")
    
    args = parser.parse_args()
    
    deploy(args.target, args.setup)

if __name__ == "__main__":
    main()
