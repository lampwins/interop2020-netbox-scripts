import json
import requests

from django.core.exceptions import ObjectDoesNotExist
from django.utils.text import slugify

from dcim.choices import DeviceStatusChoices
from dcim.models import Device, DeviceRole, DeviceType, Site
from extras.scripts import *


BASE_PATH = "http://netbox.lampwins.com:3051/api/v1"


class SnipeITImportScript(Script):

    class Meta:
        name = "Snipe IT Import"
        description = "Import new assets from Snipe IT to the given NetBox site"
        field_order = ['site']

    site = ObjectVar(
        description="Site",
        model=Site,
        display_field='name'
    )

    def run(self, data, commit):

        # Load the Snipe IT API token from file
        with open("/home/netbox/snipeit_token.json", "r") as f:
            token_data = json.load(f)
        token = token_data['token']

        # HTTP headers for each request to Snipe IT
        headers = {
            "authorization": f"Bearer {token}",
            "accept": "application/json"
        }

        # Get the location from Snipe IT that corresponds to the NetBox site
        r = requests.get(f"{BASE_PATH}/locations", params={"name": data['site'].name}, headers=headers)
        snipe_data = r.json()
        if len(snipe_data['rows']) != 1:
            self.log_failure("Site not found in Snipe IT")
            return
        location = snipe_data['rows'][0]

        # Get Snipe IT assets (devices) assigned to the location
        r = requests.get(f"{BASE_PATH}/hardware", params={"location_id": location['id']}, headers=headers)
        snipe_devices = r.json()['rows']

        # Create NetBox devices
        for snipe_device in snipe_devices:
            # Check if the device already exists by asset tag
            if not Device.objects.filter(asset_tag=snipe_device['asset_tag']).exists():
                try:
                    # Verify device type exists that matches the Snipe IT manufacturer and model
                    device_type = DeviceType.objects.get(
                        manufacturer__name=snipe_device['manufacturer']['name'],
                        model=snipe_device['model']['name']
                    )
                except ObjectDoesNotExist:
                    self.log_failure(f"Matching device type for {snipe_device['model']['name']} not found")
                    return

                try:
                    # Verify device tyrolepe exists that matches the Snipe IT category
                    device_role = DeviceRole.objects.get(
                        name=snipe_device['category']['name']
                    )
                except ObjectDoesNotExist:
                    self.log_failure(f"Matching device role for {snipe_device['category']['name']} not found")
                    return

                # Create the actual NetBox device in the site with status 'Inventory'
                name = slugify(f"{data['site'].slug}-{snipe_device['category']['name']}-{snipe_device['asset_tag']}")
                device = Device(
                    name=name.lower(),
                    site=data['site'],
                    asset_tag=snipe_device['asset_tag'],
                    serial=snipe_device['serial'],
                    device_type=device_type,
                    device_role=device_role,
                    status=DeviceStatusChoices.STATUS_INVENTORY
                )
                device.save()
                self.log_success(f"Created device {device.name}")
