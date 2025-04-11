# Migration Guide

This guide outlines the changes required to migrate from the previous version of Decluttarr, which supported only single-instance configuration for Radarr, Sonarr, Lidarr, Readarr, and Whisparr, to the new multi-instance configuration.

## What Changed

- **Multi-Instance Support:**  
  The configuration has moved from single-instance keys such as `RADARR_URL` and `RADARR_KEY` to multi-instance keys like `RADARR_INSTANCES`, which allow you to specify a list of instances. Similar changes have been made for Sonarr, Lidarr, Readarr, and Whisparr.

- **Configuration Format:**  
  For multi-instance support, the preferred configuration format is to define a JSON array of instance objects. For example:

  ```json
  RADARR_INSTANCES = [{"url": "http://radarr:7878", "key": "$RADARR_API_KEY"}]
  ```

## Migration Steps

1. **Backup Your Configuration:**  
   Always create a backup of your existing configuration file.

2. **Update the Configuration File:**  
   Edit your configuration file (`config/config.conf-Example`) and replace the single-instance keys with the new multi-instance format as shown in the examples above. While the old keys are still supported, they are deprecated and will be removed in future releases.

3. **Update Environment Variables:**  
   If you're using environment variables for configuration, ensure that you update them as necessary to support multiple instances.

4. **Test the Configuration:**  
   Run the full test suite using `pytest` to verify that everything is working as expected with the new configuration.

## Additional Recommendations

- Consider migrating to the new multi-instance keys as soon as possible to take full advantage of the updated architecture.
- Review the updated documentation in the README for more details on configuration options.

Happy migrating!
