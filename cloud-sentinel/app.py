import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ConnectTimeoutError

from flask import Flask, jsonify
app = Flask(__name__)
# CIDRs that open a port to the whole internet
OPEN_CIDRS = {'0.0.0.0/0', '::/0'}
CFG = Config(connect_timeout=5, read_timeout=15, retries={'max_attempts':2})

# Ports that should never be open to the internet
SENSITIVE_PORTS = {
    22: 'SSH',
    3389: 'RDP',
    3306: 'MySQL',
    5432: 'PostgreSQL',
    6379: 'Redis',
    27017: 'MongoDB',
}


def describe_ports(rule):
    if rule['IpProtocol'] == '-1':
        return 'all traffic'
    from_port, to_port = rule.get('FromPort'), rule.get('ToPort')
    if from_port == to_port:
        return f"{rule['IpProtocol']}/{from_port}"
    return f"{rule['IpProtocol']}/{from_port}-{to_port}"


def sensitive_ports_in(rule):
    if rule['IpProtocol'] == '-1':
        return list(SENSITIVE_PORTS.values())
    from_port, to_port = rule.get('FromPort'), rule.get('ToPort')
    return [name for port, name in SENSITIVE_PORTS.items() if from_port <= port <= to_port]


def open_cidrs_in(rule):
    cidrs = [r['CidrIp'] for r in rule.get('IpRanges', [])]
    cidrs += [r['CidrIpv6'] for r in rule.get('Ipv6Ranges', [])]
    return [cidr for cidr in cidrs if cidr in OPEN_CIDRS]


def scan(ec2, region):
    findings = []
    paginator = ec2.get_paginator('describe_security_groups')
    for page in paginator.paginate():
        for sg in page['SecurityGroups']:
            for rule in sg['IpPermissions']:
                cidrs = open_cidrs_in(rule)
                if not cidrs:
                    continue
                sensitive = sensitive_ports_in(rule)
                findings.append({
                    'group_id': sg['GroupId'],
                    'group_name': sg['GroupName'],
                    'vpc_id': sg.get('VpcId', '-'),
                    'ports': describe_ports(rule),
                    'cidrs': ', '.join(cidrs),
                    'severity': 'HIGH' if sensitive else 'MEDIUM',
                    'services': ', '.join(sensitive),
                    'region': region,
                })
    return findings

def run_scan():
    # Credentials come from the default chain: AWS_PROFILE, env vars, or an IAM role
    session = boto3.Session()
    sts = session.client('sts')
    print("Account ID:", sts.get_caller_identity()["Account"])

    ec2 = session.client('ec2')
    regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
    print("Scanning regions:", ', '.join(regions))

    combined_regional_findings = []
    for region in regions:
        print(f"\nScanning region {region}...")
        try:
            ec2 = session.client('ec2', region_name=region, config=CFG)
            combined_regional_findings.extend(scan(ec2, region))
        except (ClientError,EndpointConnectionError, ConnectTimeoutError) as e:
            print(f"Error scanning region {region}: {e}")
            continue
    

    print(f"Found {len(combined_regional_findings)} rule(s) open to the internet:")
    for f in combined_regional_findings:
        line = f"[{f['severity']}] {f['group_id']} ({f['group_name']}, {f['vpc_id']}) {f['ports']} from {f['cidrs']}"
        if f['services']:
            line += f" -> exposes {f['services']}"
        print(line)
    return combined_regional_findings

def main():
    combined_regional_findings = run_scan()
    print(f"Found {len(combined_regional_findings)} rule(s) open to the internet:")
    for f in combined_regional_findings:
        line = f"[{f['severity']}] {f['group_id']} ({f['group_name']}, {f['vpc_id']}) {f['ports']} from {f['cidrs']}"
        if f['services']:
            line += f" -> exposes {f['services']}"
        print(line)

@app.route("/findings")
def findings():
    return jsonify(run_scan())
@app.route("/health")
def health():
    return {"ok":"True"}

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
