#!/usr/bin/python

import json
import requests

from future.standard_library import install_aliases
install_aliases()

from urllib.parse import urljoin
from urllib import quote

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: mr-provisioner-machine-provision

short_description: Provision a machine in Mr. Provisioner.

description:
    Implemented:
        - Set machine's initrd, kernel
        - Provision machine
        - Wait for machine to come online
    Not implemented:
        -
        -

options:
    machine_name:
        description: Machine name
        required: true
    image_description:
        description: initrd and kernel names (should be the same)
        required: true
    preseed_name:
        description: name of preseed to use.
        required: true
    kernel_options:
        description: kernel boot command line
        required: false
    url:
        description: url to provisioner instance in the form of http://172.27.80.1:5000/
        required: true
    token:
        description: Mr. Provisioner auth token
        required: true

author:
    - Dan Rue <dan.rue@linaro.org>
'''

EXAMPLES = '''

'''

RETURN = '''

'''

from ansible.module_utils.basic import AnsibleModule

class ProvisionerError(Exception):
    def __init__(self, message):
        super(ProvisionerError, self).__init__(message)


def set_machine_parameters(url, token, machine_id, initrd_id=None,
                           kernel_id=None, preseed_id=None):
    """ Set parameters on machine specified by machine_id """
    headers = {'Authorization': token}
    url = urljoin(url, "/api/v1/machine/{}".format(machine_id))

    parameters = {}
    #if initrd_id:
    #    parameters['initrd_id'] = initrd_id
    if kernel_id:
        parameters['kernel_id'] = kernel_id
    if preseed_id:
        parameters['preseed_id'] = preseed_id
    parameters['netboot_enabled'] = True
    parameters['kernel_opts'] = ""

    put_data = {'machine': json.dumps(parameters) }

    r = requests.put(url, headers=headers, data=put_data)

    if r.status_code != 200:
        raise ProvisionerError('Error PUTing {}, HTTP {} {}, {}'.format(url,
                         r.status_code, r.reason, url))
    return r.json()

def get_machine_by_name(url, token, machine_name):
    """ Look up machine by name """
    headers = {'Authorization': token}
    q = '(= name "{}")'.format(quote(machine_name))
    url = urljoin(url, "/api/v1/machine?q={}&show_all=false".format(q))
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        raise ProvisionerError('Error fetching {}, HTTP {} {}'.format(url,
                         r.status_code, r.reason))
    if len(r.json()) == 0:
        raise ProvisionerError('Error no assigned machine found with name "{}"'.
                format(machine_name))
    if len(r.json()) > 1:
        raise ProvisionerError('Error more than one machine found with name "{}", {}'.
                format(machine_name, r.json()))
    return r.json()[0]

def get_preseed_by_name(url, token, preseed_name):
    """ Look up preseed by name """
    headers = {'Authorization': token}
    url = urljoin(url, "/api/v1/preseed?show_all=true")
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        raise ProvisionerError('Error fetching {}, HTTP {} {}'.format(url,
                         r.status_code, r.reason))
    for preseed in r.json():
        if preseed['name'] == preseed_name:
            del preseed['content'] # we don't need it, and it's really big
            return preseed

    raise ProvisionerError('Error no preseed found with name "{}"'.
            format(preseed_name))

def get_images_by_description(url, token, description):
    """ Look up images by description """
    headers = {'Authorization': token}
    url = urljoin(url, "/api/v1/image?show_all=false")
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        raise ProvisionerError('Error fetching {}, HTTP {} {}'.format(url,
                         r.status_code, r.reason))
    images = {'Kernel': None, 'Initrd': None}
    for image in r.json():
        if (image['description'] == description):
            if images[image['type']] is not None:
                # Error, duplicate image of same description found
                msg = (
                "Error, duplicate {} images found with description '{}' and owner {}"                    .format(image['type'], image['description'], image['user']))
                raise ProvisionerError(msg)
            images[image['type']] = image
    if (images['Kernel'] is None or
        images['Initrd'] is None):
        msg = "Error finding images matching description '{}'. Found {}".format(
            description, images)
        raise ProvisionerError(msg)
    return images['Kernel'], images['Initrd']

def run_module():
    # define the available arguments/parameters that a user can pass to
    # the module
    module_args = dict(
        machine_name=dict(type='str', required=True),
        image_description=dict(type='str', required=True),
        preseed_name=dict(type='str', required=True),
        kernel_options=dict(type='str', required=False),
        url=dict(type='str', required=True),
        token=dict(type='str', required=True),
    )

    result = dict(
        changed=False,
        debug={},
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if module.check_mode:
        return result


    # Look up machine, verify assignment
    try:
        machine = get_machine_by_name(module.params['url'],
                                      module.params['token'],
                                      module.params['machine_name'])
    except ProvisionerError, e:
        module.fail_json(msg=str(e), **result)
    result['debug']['machine'] = machine

    # Look up kernel, initrd
    try:
        kernel_id, initrd_id = get_images_by_description(module.params['url'],
                                         module.params['token'],
                                         module.params['image_description'])
    except ProvisionerError, e:
        module.fail_json(msg=str(e), **result)
    result['debug']['kernel_id'] = kernel_id
    result['debug']['initrd_id'] = initrd_id

    # Look up kernel, initrd, and preseed IDs
    try:
        preseed = get_preseed_by_name(module.params['url'],
                                      module.params['token'],
                                      module.params['preseed_name'])
    except ProvisionerError, e:
        module.fail_json(msg=str(e), **result)
    result['debug']['preseed'] = preseed

    # Set kernel, initrd, preseed on machine
    try:
        machine_state = set_machine_parameters(module.params['url'],
                                      module.params['token'],
                                      machine_id=machine['id'],
                                      initrd_id=initrd_id['id'],
                                      kernel_id=kernel_id['id'],
                                      preseed_id=preseed['id'])

    except ProvisionerError, e:
        module.fail_json(msg=str(e), **result)
    result['machine_state'] = machine_state

    # Reboot/provision

    module.fail_json(msg="{}, {}".format(kernel_id, initrd_id), **result)


    # Image does not yet exist. Upload it.
    # curl -X POST "http://172.27.80.1:5000/api/v1/image"
    # -H "accept: application/json"
    # -H "Authorization: DEADBEEF"
    # -H "content-type: multipart/form-data"
    # -F "file=@linux;type="
    # -F "q={ "description": "Example image",
    #         "type": "Kernel",
    #         "public": false,
    #         "known_good": true } "
#    headers = {'Authorization': module.params['token']}
#    url = urljoin(module.params['url'], "/api/v1/image")
#    files = {'file': open(module.params['path'], 'rb')}
#    data = {'q': json.dumps({
#                 'description': module.params['description'],
#                 'type': module.params['type'],
#                 'known_good': module.params['known_good'],
#                 'public': module.params['public'],
#             })
#           }
#    r = requests.post(url, files=files, data=data, headers=headers)
#    if r.status_code != 201:
#        msg = ("Error fetching {}, HTTP {} {}\nrequest data: {}\nresult json: {}".
#                format(url, r.status_code, r.reason, data, r.json()))
#        module.fail_json(msg=msg, **result)
#    result['json'] = r.json()
#    result['changed'] = True

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()
