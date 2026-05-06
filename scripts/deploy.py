import argparse
import subprocess
import sys
import os
import tarfile
from pathlib import Path

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
            print_step("Restarting the logger and GPS services...")
            # Restart the services and show the status/latest logs so the user knows it succeeded
            restart_cmd = f"sudo systemctl restart {project_name} wolftrack-gps && echo '' && sudo systemctl status {project_name} wolftrack-gps --no-pager"
            run_cmd(["ssh", "-t", target_ssh, restart_cmd])
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
