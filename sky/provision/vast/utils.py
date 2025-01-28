# pylint: disable=assignment-from-no-return
#
# The pylint exception above is an accomodation for
# false positives generated by pylint for the Vast
# python sdk.
#
"""Vast library wrapper for SkyPilot."""
from typing import Any, Dict, List

from sky import sky_logging
from sky.adaptors import vast

logger = sky_logging.init_logger(__name__)


def list_instances() -> Dict[str, Dict[str, Any]]:
    """Lists instances associated with API key."""
    instances = vast.vast().show_instances()

    instance_dict: Dict[str, Dict[str, Any]] = {}
    for instance in instances:
        instance['id'] = str(instance['id'])
        info = instance

        if isinstance(instance['actual_status'], str):
            info['status'] = instance['actual_status'].upper()
        else:
            info['status'] = 'UNKNOWN'
        info['name'] = instance['label']

        instance_dict[instance['id']] = info

    return instance_dict


def launch(name: str, instance_type: str, region: str, disk_size: int,
           image_name: str, preemptible: bool) -> str:
    """Launches an instance with the given parameters.

    Converts the instance_type to the Vast GPU name, finds the specs for the
    GPU, and launches the instance.

    Notes:

      *  `disk_size`: we look for instances that are of the requested
         size or greater than it. For instance, `disk_size=100` might
         return something with `disk_size` at 102 or even 1000.

         The disk size {xx} GB is not exactly matched the requested
         size {yy} GB. It is possible to charge extra cost on disk.

      *  `geolocation`: Geolocation on Vast can be as specific as the
         host chooses to be. They can say, for instance, "Yutakachō,
         Shinagawa District, Tokyo, JP." Such a specific geolocation
         as ours would fail to return this host in a simple string
         comparison if a user searched for "JP".

         Since regardless of specificity, all our geolocations end
         in two-letter country codes we just snip that to conform
         to how many providers state their geolocation.

      *  Since the catalog is cached, we can't gaurantee availability
         of any machine at the point of inquiry.  As a consequence we
         search for the machine again and potentially return a failure
         if there is no availability.

	  *  We pass in the cpu_ram here as a guarantor to make sure the
		 instance we match with will be compliant with the requested
		 amount of memory.

      *  Vast instance types are an invention for skypilot. Refer to
         service_catalog/vast_catalog.py for the current construction
         of the type.

    """
    cpu_ram  = float(instance_type.split('-')[-1])/1024
    gpu_name = instance_type.split('-')[1].replace('_', ' ')
    num_gpus = int(instance_type.split('-')[0].replace('x', ''))

    query = ' '.join([
        f'geolocation="{region[-2:]}"',
        f'disk_space>={disk_size}',
        f'num_gpus={num_gpus}',
        f'gpu_name="{gpu_name}"',
        f'cpu_ram>="{cpu_ram}"',
    ])

    instance_list = vast.vast().search_offers(query=query)

    if isinstance(instance_list, int) or len(instance_list) == 0:
        return ''

    instance_touse = instance_list[0]

    launch_params = {
        'id': instance_touse['id'],
        'direct': True,
        'ssh': True,
        'env': '-e __SOURCE=skypilot',
        'onstart_cmd': ';'.join([
            'touch ~/.no_auto_tmux',
            f'echo "{vast.vast().api_key_access}" > ~/.vast_api_key',
        ]),
        'label': name,
        'image': image_name
    }

    if preemptible:
        launch_params['min_bid'] = instance_touse['min_bid']

    new_instance_contract = vast.vast().create_instance(**launch_params)

    new_instance = vast.vast().show_instance(
        id=new_instance_contract['new_contract'])

    return new_instance['id']


def start(instance_id: str) -> None:
    """Starts the given instance."""
    vast.vast().start_instance(id=instance_id)


def stop(instance_id: str) -> None:
    """Stops the given instance."""
    vast.vast().stop_instance(id=instance_id)


def remove(instance_id: str) -> None:
    """Terminates the given instance."""
    vast.vast().destroy_instance(id=instance_id)


def get_ssh_ports(cluster_name: str) -> List[int]:
    """Gets the SSH ports for the given cluster."""
    logger.debug(f'Getting SSH ports for cluster {cluster_name}.')

    instances = list_instances()
    possible_names = [f'{cluster_name}-head', f'{cluster_name}-worker']

    ssh_ports = []

    for instance in instances.values():
        if instance['name'] in possible_names:
            ssh_ports.append(instance['ssh_port'])
    assert ssh_ports, (
        f'Could not find any instances for cluster {cluster_name}.')

    return ssh_ports
