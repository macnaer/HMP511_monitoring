FROM jasonrivers/nagios:latest

COPY nagios.cfg /opt/nagios/etc/nagios.cfg
COPY monitor/ping-file.cfg /opt/nagios/etc/monitor/ping-file.cfg

EXPOSE 81
