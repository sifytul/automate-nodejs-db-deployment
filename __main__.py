import pulumi
import pulumi_aws as aws
import os


vpc = aws.ec2.Vpc(
    "nodejs-db-vpc",
    cidr_block="16.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={
        "Name": "nodejs-db-vpc"
    }
)

public_subnet = aws.ec2.Subnet(
    "public-subnet",
    cidr_block="16.0.1.0/24",
    availability_zone="ap-southeast-1a",
    map_public_ip_on_launch=True,
    vpc_id=vpc.id,
    tags={
        "Name": "public-subnet"
    }
)

private_subnet = aws.ec2.Subnet(
    "private-subnet",
    cidr_block="16.0.2.0/24",
    map_public_ip_on_launch=False,
    availability_zone="ap-southeast-1a",
    vpc_id=vpc.id,
    tags={
        "Name": "private-subnet"
    }
)

internet_gateway = aws.ec2.InternetGateway(
    "internet-gateway",
    vpc_id=vpc.id,
    tags={
        "Name": "internet-gateway"
    }
)

elastic_ip = aws.ec2.Eip(
    "eip"
)

nat_gateway = aws.ec2.NatGateway(
    "nat-gateway",
    allocation_id=elastic_ip.id,
    subnet_id=public_subnet.id,
    tags= {
        "Name": "nat-gateway"
    }
)

public_route_table = aws.ec2.RouteTable(
    "public-route-table",
    vpc_id=vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=internet_gateway.id
        )
    ]
)

private_route_table = aws.ec2.RouteTable(
    "private-route-table",
    vpc_id=vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            nat_gateway_id=nat_gateway.id
        )
    ]
)

public_route_table_association = aws.ec2.RouteTableAssociation(
    "public-route-table-association",
    subnet_id=public_subnet.id,
    route_table_id=public_route_table.id
)

private_route_table_association = aws.ec2.RouteTableAssociation(
    "private-route-table-association",
    subnet_id=private_subnet.id,
    route_table_id=private_route_table.id
)

nodejs_security_group = aws.ec2.SecurityGroup(
    "nodejs-security-group",
    vpc_id=vpc.id,
    description="nodejs security groups",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=22,
            to_port=22,
            cidr_blocks=["0.0.0.0/0"]
        ),
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=3000,
            to_port=3000,
            cidr_blocks=["0.0.0.0/0"]
        ),

    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"]
        ),
    ]
)

db_security_group = aws.ec2.SecurityGroup(
    "db-security-group",
    vpc_id=vpc.id,
    description="db security groups",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=22,
            to_port=22,
            cidr_blocks=[public_subnet.cidr_block]
        ),
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=3306,
            to_port=3306,
            cidr_blocks=[public_subnet.cidr_block]
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"]
        ),
    ],
    tags= {
        "Name": "db-security-group"
    }
)

with open("/root/code/script/mysql-setup.sh", "r") as file:
    print("Reading from mysql-setup script...")
    mysql_setup_script = file.read()

def generate_db_user_data():
    script=f'''#!/bin/bash

    cat > >(tee /var/log/mysql-setup.log) 2>&1

    apt-get update
    apt-get upgrade -y

    mkdir -p /usr/local/bin

    cat > /usr/local/bin/mysql-setup.sh << 'EOL'
    {mysql_setup_script}
    EOL

    chmod +x /usr/local/bin/mysql-setup.sh

    bash /usr/local/bin/mysql-setup.sh
    '''
    return script



db = aws.ec2.Instance(
    "db-instance",
    ami="ami-01811d4912b4ccb26",
    instance_type="t2.micro",
    key_name="db-cluster",
    subnet_id=private_subnet.id,
    vpc_security_group_ids=[db_security_group],
    user_data=generate_db_user_data(),
    opts=pulumi.ResourceOptions(
        depends_on=[
            nat_gateway,
            private_route_table_association,
            private_subnet
        ]
    ),
    tags={
        "Name": "db-instance"
    }
)

with open('/root/code/script/nodejs-setup.sh', 'r') as file:
    print("Reading from nodejs setup script...")
    nodejs_setup_script = file.read()


with open('/root/code/script/check-mysql.sh', 'r') as file:
    print("Reading from check-mysql script...")
    check_mysql_script = file.read()


def generate_nodejs_user_data(db_private_ip):
    script = f"""#!/bin/bash

    exec > >(tee /var/log/nodejs-setup-log.log) 2>&1

    apt-get update
    apt-get upgrade -y

    echo "DB_PRIVATE_IP={db_private_ip}" >> /etc/environment
    source /etc/environment

    mkdir -p /tmp/scripts

    cat > /tmp/scripts/nodejs-setup.sh << 'EOL'
    {nodejs_setup_script}
    EOL

    cat > /tmp/scripts/check-mysql.sh << 'EOL'
    {check_mysql_script}
    EOL

    chmod +x /tmp/scripts/nodejs-setup.sh
    bash /tmp/scripts/nodejs-setup.sh
    """


nodejs = aws.ec2.Instance(
    "nodejs-instance",
    ami="ami-01811d4912b4ccb26",
    instance_type="t2.micro",
    key_name="db-cluster",
    subnet_id=public_subnet.id,
    vpc_security_group_ids=[nodejs_security_group],
    associate_public_ip_address=True,
    user_data=pulumi.Output.all(db.private_ip).apply(
        lambda args: generate_nodejs_user_data(args[0])
    ),
    user_data_replace_on_change=True,
    tags={
        "Name": "nodejs-instance"
    }
)

# Export Public and Private IPs
pulumi.export('nodejs_public_ip', nodejs.public_ip)
pulumi.export('nodejs_private_ip', nodejs.private_ip)
pulumi.export('db_private_ip', db.private_ip)

# Export the VPC ID and Subnet IDs for reference
pulumi.export('vpc_id', vpc.id)
pulumi.export('public_subnet_id', public_subnet.id)
pulumi.export('private_subnet_id', private_subnet.id)

# Create config file
def create_config_file(all_ips):
    config_content = f"""Host nodejs-server
    HostName {all_ips[0]}
    User ubuntu
    IdentityFile ~/.ssh/db-cluster.id_rsa

Host db-server
    ProxyJump nodejs-server
    HostName {all_ips[1]}
    User ubuntu
    IdentityFile ~/.ssh/db-cluster.id_rsa
"""
    
    config_path = os.path.expanduser("~/.ssh/config")
    with open(config_path, "w") as config_file:
        config_file.write(config_content)

# Collect the IPs for all nodes
all_ips = [nodejs.public_ip, db.private_ip]

# Create the config file with the IPs once the instances are ready
pulumi.Output.all(*all_ips).apply(create_config_file)
