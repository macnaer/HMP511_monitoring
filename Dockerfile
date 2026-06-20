FROM jasonrivers/nagios:latest

COPY nagios.cfg /opt/nagios/etc/nagios.cfg
COPY monitor/*.cfg /opt/nagios/etc/monitor/

EXPOSE 81
