# plugin.sh - Devstack plugin.sh script to install and configure slogging with swift settings

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set -o xtrace

echo_summary "slogging's plugin.sh was called..."
source $DEST/slogging/devstack/lib/slogging

# check for service enabled
if is_plugin_enabled slogging; then

    if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
        # Set up system services                  # apt-get install, pip insall
        #echo_summary "Configuring system services Slogging"
        #install_package cowsay
        :

    elif [[ "$1" == "stack" && "$2" == "install" ]]; then
        # Perform installation of service source  # python setup.py install
        #echo_summary "Installing Slogging"
        #install_slogging
        :

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        # Configure after the other layer 1 and 2 services have been configured
        echo_summary "Configuring Slogging"  # memcached, rsyslog, ... etc
        configure_slogging

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        # Initialize and start the
        echo_summary "Verifying Swift nomally installed"
        verify_swift

    elif [[ "$1" == "stack" && "$2" == "test-config" ]]; then
        # Unit & Function test for slogging to get swift log
        echo_summary "Metering Sample with Swift"
        metering-sample_slogging
    fi

    if [[ "$1" == "unstack" ]]; then
        # Shut down template services
        # no-op
        :
    fi

    if [[ "$1" == "clean" ]]; then
        # Remove state and transient data
        # Remember clean.sh first calls unstack.sh
        # no-op
        :
    fi
fi

# Restore
$XTRACE

