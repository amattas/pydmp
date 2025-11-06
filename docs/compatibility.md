# Panel Compatibility

PyDMP aims to support all DMP panels with TCP/IP capability. This page tracks tested hardware and community-reported compatibility.

**Have a different panel?** Your testing helps expand support. Submit a [compatibility report](https://github.com/amattas/pydmp/issues/new?template=panel_compatibility.yml) to help other users.

## Compatibility Status Legend

- **Fully Tested**: Extensively tested, all features confirmed working
- **Tested**: Basic functionality confirmed working
- **Reported Working**: Community reports indicate compatibility
- **Untested**: No testing data available
- **Partially Working**: Some features work, others have known issues
- **Not Compatible**: Known incompatibilities

## Tested Panels

### XR150

**Status**: Fully Tested

| Feature | Status | Notes |
|---------|--------|-------|
| Connection/Authentication | Working | TCP/IP on port 2011 |
| Area Arm/Disarm | Working | All arm modes supported |
| Zone Status | Working | Real-time status updates |
| Zone Bypass/Restore | Working | Individual zone control |
| Output Control | Working | On/Off/Pulse/Toggle |
| User Management | Working | User code validation |
| Profile Management | Working | Profile retrieval |
| Status Updates (S3) | Working | Real-time event streaming |

**Panel Details**:

- Firmware Version: 2.45 (tested)
- Hardware Revision: Rev 3.0
- Connection: Direct Ethernet
- Network: TCP/IP, Port 2011

**Configuration Notes**:

- Ensure TCP/IP communication is enabled on the panel
- Remote key must be configured in panel settings
- Account number must be zero-padded to 5 digits (e.g., "00001")

**Known Issues**: None

**Last Tested**: 2025-01 with PyDMP v0.1.0

---

## Community Reported Panels

### XR550

**Status**: Untested (Awaiting Reports)

The XR550 is expected to work as it uses the same protocol as the XR150, but we need community confirmation.

**Expected Compatibility**: High
**Protocol**: DMP TCP/IP (same as XR150)

If you have an XR550, please test and [report compatibility](https://github.com/amattas/pydmp/issues/new?template=panel_compatibility.yml).

---

### XR2500

**Status**: Untested (Awaiting Reports)

**Expected Compatibility**: High
**Protocol**: DMP TCP/IP (same as XR150)

If you have an XR2500, please test and [report compatibility](https://github.com/amattas/pydmp/issues/new?template=panel_compatibility.yml).

---

### XT30 / XT50

**Status**: Untested (Awaiting Reports)

The XT series panels use similar DMP protocols but may have feature differences.

**Expected Compatibility**: Medium to High
**Protocol**: DMP TCP/IP

If you have an XT30 or XT50, please test and [report compatibility](https://github.com/amattas/pydmp/issues/new?template=panel_compatibility.yml).

---

## How to Report Compatibility

Have you tested PyDMP with a DMP panel not listed here? We would appreciate your feedback.

1. **Test the panel** with PyDMP using the Quick Start guide
2. **Document your findings** - which features work, which do not
3. **Submit a compatibility report** using our [Panel Compatibility Report](https://github.com/amattas/pydmp/issues/new?template=panel_compatibility.yml) template

Please include:

- Panel model number
- Firmware version
- Hardware revision (if known)
- Features tested and their status
- Any configuration notes or quirks

## Panel Requirements

For PyDMP to work with your panel, it must support:

- **TCP/IP Communication**: Panel must have network connectivity
- **DMP Protocol**: Must support DMP's proprietary TCP protocol
- **Remote Access**: Remote key authentication must be enabled
- **Port 2011**: Default DMP communication port (may be configurable)

## Firmware Considerations

Different firmware versions may have different features or behaviors. If you experience issues:

1. Check your firmware version (usually shown on panel display or settings)
2. Consult DMP documentation for your specific firmware
3. Report compatibility with your firmware version
4. Consider upgrading to the latest firmware (contact DMP dealer)

## Network Topologies

PyDMP has been tested in the following network configurations:

### Direct Connection

- Panel to Switch to Computer (same LAN)
- **Status**: Working
- **Latency**: Less than 10ms typical
- **Recommended for**: Local installations

### WiFi

- Panel to WiFi Bridge to Router to Computer
- **Status**: Working
- **Latency**: 10-50ms typical
- **Notes**: Ensure stable WiFi connection

### VPN/Remote

- Panel to Internet to VPN to Remote Computer
- **Status**: Working
- **Latency**: 50-200ms typical
- **Notes**: Port forwarding or VPN required, consider timeout settings

### Serial to Ethernet

- Panel (Serial) to Serial-to-Ethernet Converter to Network
- **Status**: Untested
- **Notes**: Should work if converter properly configured for DMP protocol

## Troubleshooting Compatibility Issues

If you are having issues with an unlisted panel:

1. **Verify network connectivity**: Can you ping the panel?
2. **Check port access**: Is port 2011 open and accessible?
3. **Test authentication**: Do you have the correct remote key and account number?
4. **Enable debug logging**: Run with `--debug` flag for detailed output
5. **Review panel documentation**: Ensure TCP/IP features are enabled
6. **Report the issue**: Use our [Bug Report](https://github.com/amattas/pydmp/issues/new?template=bug_report.yml) template

## Future Panel Support

We aim to support all DMP panels that use the TCP/IP protocol. If you have a panel not listed here, we encourage you to:

- Test it and report your findings
- Share any protocol differences you discover
- Contribute panel-specific code if needed

Your feedback helps make PyDMP better for everyone.

## Reference Documentation

- [DMP Official Website](https://www.dmp.com/)
- [PyDMP Documentation](https://amattas.github.io/pydmp/)
- [Panel Programming Guides](https://www.dmp.com/resources) (requires DMP dealer login)

---

**Last Updated**: 2025-01-06

**Maintainer Note**: This document is community-driven. Panel compatibility is based on testing and user reports. If you have updates or corrections, please submit a pull request or open an issue.
