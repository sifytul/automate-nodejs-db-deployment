#!/bin/bash

exec > >(tee /var/log/mysql-setup.log) 2>&1

apt-get update
apt-get install -y mysql-server

sed -i 's/^bind-address:.*/bind-address: 0.0.0.0/'  /etc/mysql/mysql.conf.d/mysqld.cnf

mysql -e "CREATE DATABASE practice_app;"
mysql -e "CREATE USER 'app_user'@'%' IDENTIFIED BY 'password';"
mysql -e "GRANT ALL PRIVILEGES ON practice_app TO 'app_user'@'%';"
mysql -e "FLUSH PRIVILEGES;"

mysql -e "CREATE TABLE users(
    id INT AUTO_INCREMENT,
    name VARCHAR(100),
    email VARCHAR(50),
    register_date DATETIME,
    PRIMARY KEY(id)
    );"

mysql -e "INSERT INTO users (name, email, register_date) VALUES ('Fred', 'fred@gmail.com;, now()), ('Sara', 'sara@gmail.com', now()), ('Pato', 'pato@gmail.com', now());"

systemctl restart mysql