# Auto-Start Porting Prompt and Method (Windows)

Use this when you want another engineer (or Codex agent) to replicate the same
boot start + crash restart behavior in a different app.

## 1. How the current app works

This repo uses `NSSM + Windows Service` as the reliability pattern, not Startup
folder or Task Scheduler.

Primary references:
- `install_middleware_service.bat`
- `uninstall_middleware_service.bat`
- `DEPLOYMENT_CHECKLIST.md`

Key mechanics in `install_middleware_service.bat`:
- Self-elevates to admin before service operations (`net session` check, lines 10-14).
- Installs service via NSSM, running Python entrypoint:
  - `nssm install ... python.exe main.py --host --port` (line 103).
- Enables boot auto-start:
  - `nssm set ... Start SERVICE_AUTO_START` (line 113).
- Enables app-level restart when process exits/crashes:
  - `nssm set ... AppExit Default Restart` (line 119).
  - `nssm set ... AppRestartDelay 5000` (line 120).
  - `nssm set ... AppThrottle 1500` (line 121).
- Enables Windows Service Control Manager recovery:
  - `sc failure ... restart/5000/restart/5000/restart/5000` (line 125).
  - `sc failureflag ... 1` (line 126).
- Writes service logs to files for diagnostics (lines 114-118, 149-151).

This gives:
- Start on Windows boot, without user login.
- Restart on sudden app close/crash.
- Operational logs for postmortem debugging.

## 2. Failure behavior matrix

- PC reboot:
  - Windows Service Manager starts the service automatically (Auto Start).
- App process crash / sudden close:
  - NSSM and SCM recovery restart the process after configured delay.
- Power outage:
  - Service starts on OS boot only after machine powers on.
  - BIOS/UEFI "Restore on AC Power Loss" decides whether machine auto-powers.
- User logoff:
  - Service continues (headless background service).

## 3. Super prompt for Codex (copy/paste)

```text
You are a senior Windows reliability engineer. Port the exact auto-start and auto-restart pattern from this source app into a target app.

Objective:
- On Windows boot, target app starts automatically without user login.
- If target process crashes or closes unexpectedly, it restarts automatically.
- Add clean install/uninstall scripts and a validation checklist.

Source pattern to replicate:
- NSSM-managed Windows Service, not Startup folder/Task Scheduler (for API/headless services).
- Service auto-start type: SERVICE_AUTO_START.
- App-level restart policy: AppExit Default Restart, AppRestartDelay 5000, AppThrottle 1500.
- SCM recovery policy: sc failure reset=86400 actions=restart/5000/restart/5000/restart/5000 and sc failureflag 1.
- Log redirection for stdout/stderr with rotation.
- Installer self-elevation to admin and safe preflight checks.

Required deliverables:
1) install_<target>_service.bat
2) uninstall_<target>_service.bat
3) deployment doc section: "Windows Auto-Start + Auto-Restart"
4) exact verification commands and expected outputs

Implementation requirements:
- Reuse target app's real entrypoint and venv path.
- Resolve service name, display name, working directory, host/port/env vars from target app.
- Validate prerequisites (python executable, entrypoint file, logs directory).
- If NSSM is missing: use local nssm.exe if bundled, otherwise PATH, otherwise fail with actionable message.
- Reinstall logic must be idempotent: stop/remove existing service before install.
- Set AppDirectory to project root.
- Configure AppEnvironmentExtra for required runtime environment variables.
- Configure stdout/stderr file paths and rotation.
- Start service after install and print status/help commands.

Testing requirements (must run and report):
- Install test: service reaches RUNNING.
- Reboot persistence test: after reboot, service returns RUNNING automatically.
- Crash recovery test: kill the child process, verify service restarts within expected delay.
- Port binding test: expected listening port is active after restart.
- Health endpoint test (if HTTP app): returns healthy after restart.

Output format:
- Show changed files first.
- Then show exact commands executed.
- Then show test results with pass/fail.
- Then list residual risks and rollback steps.

Non-goals:
- Do not use Startup folder or VBS startup hacks for headless API services.
- Do not require user login to keep app alive.
```

## 4. Porting method for any other app

1. Classify app type.
- If headless API/worker: use `NSSM + Windows Service`.
- If interactive GUI/tray app: evaluate Task Scheduler/Startup pattern separately.

2. Identify runtime contract.
- Absolute path to executable (`python.exe`, `node.exe`, or app binary).
- Absolute path to entrypoint/script.
- Startup args (`--host`, `--port`, etc.).
- Required environment variables.

3. Build installer script.
- Add admin self-elevation.
- Validate executable and entrypoint exist.
- Ensure logs directory exists.
- Acquire NSSM (local file or PATH).
- Stop/remove old service idempotently.
- Install service command.
- Apply NSSM settings:
  - DisplayName, Description, AppDirectory
  - Start `SERVICE_AUTO_START`
  - AppExit restart policy
  - AppRestartDelay/AppThrottle
  - AppEnvironmentExtra
  - AppStdout/AppStderr + rotation
- Apply SCM recovery policy (`sc failure`, `sc failureflag`).
- Start service and print operational commands.

4. Build uninstall script.
- Stop service.
- Remove service via NSSM (if available) or `sc`.
- Delete service registration with `sc delete`.
- Keep logs by default.

5. Validate operationally.
- `sc query <ServiceName>`
- `netstat -ano | Select-String ':<PORT>'`
- `Invoke-RestMethod http://127.0.0.1:<PORT>/health` (if HTTP)
- Crash simulation and automatic restart validation.

6. Document recovery boundaries.
- App restarts on process crash.
- Service restarts on OS boot.
- Full power-loss recovery depends on BIOS/UEFI power restoration settings.

## 5. Common mistakes to avoid

- Using Startup folder for a backend API service.
- Forgetting `SERVICE_AUTO_START`.
- Setting restart policy only in NSSM but not SCM (or vice versa).
- Relative paths in service config (use absolute paths).
- No log capture for service stdout/stderr.
- Missing admin elevation, causing silent install failures.
- Not testing forced crash recovery explicitly.
