FROM jasonrivers/nagios:latest

# Install Python 3 and dependencies for custom checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    sshpass \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages for Nagios checks
RUN pip3 install --no-cache-dir --break-system-packages \
    "pyasn1>=0.5.0" \
    "pysnmp>=5.0.0" \
    "psutil>=5.9.0" \
    "paramiko>=2.12.0"

# Set default SNMP community
ENV NAGIOS_SNMP_COMMUNITY=LibreNms
ENV NAGIOS_SNMP_VERSION=2c

# Copy Nagios configuration
COPY nagios.cfg /opt/nagios/etc/nagios.cfg
COPY objects/ /opt/nagios/etc/objects/

# Copy custom scripts (bash + Python)
COPY scripts/ /opt/nagios/etc/scripts/
COPY .agents/skills/nagios-snmp/scripts/*.py /opt/nagios/etc/scripts/
COPY .agents/skills/nagios-system/scripts/*.py /opt/nagios/etc/scripts/
COPY .agents/skills/nagios-network/scripts/*.py /opt/nagios/etc/scripts/

# Set permissions
RUN chown -R nagios:nagios /opt/nagios/etc \
    && chmod +x /opt/nagios/etc/scripts/*.sh \
    && chmod +x /opt/nagios/etc/scripts/*.py

EXPOSE 81
