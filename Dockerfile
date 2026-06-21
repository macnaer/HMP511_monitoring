FROM jasonrivers/nagios:latest

COPY nagios.cfg /opt/nagios/etc/nagios.cfg
COPY objects/ /opt/nagios/etc/objects/
COPY scripts/ /opt/nagios/etc/scripts/

RUN chown -R nagios:nagios /opt/nagios/etc && chmod +x /opt/nagios/etc/scripts/*.sh

EXPOSE 81
