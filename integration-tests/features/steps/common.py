from behave import given, when, then
from hamcrest import assert_that, equal_to, not_none

import json
import pathlib
import subprocess
import requests

_TEST_DIR = pathlib.Path(__file__).parent.parent.parent
_REPO_DIR = _TEST_DIR.parent
_VM_DEFS = {path.name: str(path) for path in (_TEST_DIR / "vmdefs").iterdir()}
_LEAPP_TOOL = str(_REPO_DIR / "leapp-tool.py")


# Command execution helper
def _run_command(cmd, work_dir, ignore_errors):
    output = None
    try:
        output = subprocess.check_output(
            cmd, cwd=work_dir, stderr=subprocess.PIPE
        ).decode()
    except subprocess.CalledProcessError as exc:
        if not ignore_errors:
            print(exc.stderr.decode())
            raise
        output = exc.output.decode()
    return output

##############################
# Local VM management
##############################

def _run_vagrant(vm_def, *args, ignore_errors=False):
    # TODO: explore https://pypi.python.org/pypi/python-vagrant
    #       That may require sudo-less access to vagrant
    vm_dir = _VM_DEFS[vm_def]
    cmd = ["sudo", "vagrant"]
    cmd.extend(args)
    return _run_command(cmd, vm_dir, ignore_errors)

def _vm_up(vm_def):
    result = _run_vagrant(vm_def, "up")
    print("Started {} VM instance".format(vm_def))
    return result

def _vm_down(vm_def):
    result = _run_vagrant(vm_def, "down", ignore_errors=True)
    print("Suspended {} VM instance".format(vm_def))
    return result

def _vm_destroy(vm_def):
    result = _run_vagrant(vm_def, "destroy", ignore_errors=True)
    print("Destroyed {} VM instance".format(vm_def))
    return result


@given("the local virtual machines")
def create_local_machines(context):
    context.machines = machines = {}
    for row in context.table:
        vm_name = row["name"]
        vm_def = row["definition"]
        if vm_def not in _VM_DEFS:
            raise ValueError("Unknown VM image: {}".format(vm_def))
        ensure_fresh = (row["ensure_fresh"].lower() == "yes")
        if ensure_fresh:
            _vm_destroy(vm_def)
        _vm_up(vm_def)
        if ensure_fresh:
            context.resource_manager.callback(_vm_destroy, vm_def)
        else:
            context.resource_manager.callback(_vm_down, vm_def)
        machines[vm_name] = vm_def


##############################
# Leapp commands
##############################

def _run_leapp(*args):
    cmd = ["sudo", "/usr/bin/python2", _LEAPP_TOOL]
    cmd.extend(args)
    # Using _REPO_DIR as work_dir is a kludge to enable
    # the existing SSH kludge in leapp-tool itself,
    # which in turn relies on the tool only being used
    # with particular predefined Vagrant configurations
    return _run_command(cmd, work_dir=str(_REPO_DIR), ignore_errors=False)

def _convert_vm_to_macrocontainer(source_def, target_def):
    result = _run_leapp("migrate-machine", "-t", target_def, source_def)
    msg = "Redeployed {} as macrocontainer on {}"
    print(msg.format(source_def, target_def))
    return result

def _get_leapp_ip(machine):
    raw_ip = machine["ip"][0]
    if raw_ip.startswith("ipv4-"):
        return raw_ip[5:]
    return raw_ip

def _get_ip_addresses(source_def, target_def):
    leapp_output = _run_leapp("list-machines", "--shallow")
    machine_info = json.loads(leapp_output)
    source_ip = target_ip = None
    for machine in machine_info["machines"]:
        if machine["name"] == source_def:
            source_ip = _get_leapp_ip(machine)
        if machine["name"] == target_def:
            target_ip = _get_leapp_ip(machine)
        if source_ip is not None and target_ip is not None:
            break
    return source_ip, target_ip

@when("{source_vm} is redeployed to {target_vm} as a macrocontainer")
def redeploy_vm_as_macrocontainer(context, source_vm, target_vm):
    context.redeployment_source = source_vm
    context.redeployment_target = target_vm
    machines = context.machines
    source_def = machines[source_vm]
    target_def = machines[target_vm]
    _convert_vm_to_macrocontainer(source_def, target_def)
    source_ip, target_ip = _get_ip_addresses(source_def, target_def)
    context.redeployment_source_ip = source_ip
    context.redeployment_target_ip = target_ip


##############################
# Service status checking
##############################
def _compare_responses(original_ip, redeployed_ip, *, tcp_port, status):
    original_url = "http://{}:{}".format(original_ip, tcp_port)
    original_response = requests.get(original_url)
    assert_that(original_response.status, status, "Original status")
    redeployed_url = "http://{}:{}".format(redeployed_ip, tcp_port)
    redeployed_response = requests.get(redeployed_response)
    assert_that(redeployed_response.status, status, "Redeployed status")
    original_data = original_response.body
    redeployed_data = redeployed_response.body
    assert_that(redeployed_data, equal_to(original_body), "Same response")

@then("the HTTP responses on port {tcp_port} should match")
def check_http_responses_match(context, tcp_port):
    original_ip = context.redeployment_source_ip
    assert_that(original_ip, not_none(), "Valid original IP")
    redeployed_ip = context.redeployment_target_ip
    assert_that(redeployed_ip, not_none(), "Valid redeployment IP")
    _compare_responses(original_ip, redeployed_ip, tcp_port=80, status=200)
