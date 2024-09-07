#!/usr/bin/env python3
"""Docker From Scratch Workshop - Level 2: Adding mount namespace.

Goal: Separate our mount table from the other processes.

Usage:
    running:
        rd.py run -i ubuntu /bin/sh
    will:
        - fork a new chrooted process in a new mount namespace
"""



import linux
import tarfile
import uuid

import click
import os
import traceback
import stat


def _get_image_path(image_name, image_dir, image_suffix='tar'):
    return os.path.join(image_dir, os.extsep.join([image_name, image_suffix]))


def _get_container_path(container_id, container_dir, *subdir_names):
    return os.path.join(container_dir, container_id, *subdir_names)


def create_container_root(image_name, image_dir, container_id, container_dir):
    image_path = _get_image_path(image_name, image_dir)
    container_root = _get_container_path(container_id, container_dir, 'rootfs')

    assert os.path.exists(image_path), "unable to locate image %s" % image_name

    if not os.path.exists(container_root):
        os.makedirs(container_root)

    with tarfile.open(image_path) as t:
        # Fun fact: tar files may contain *nix devices! *facepalm*
        members = [m for m in t.getmembers()
                   if m.type not in (tarfile.CHRTYPE, tarfile.BLKTYPE)]
        t.extractall(container_root, members=members)

    return container_root


@click.group()
def cli():
    pass


def makedev(dev_path):
    for i, dev in enumerate(['stdin', 'stdout', 'stderr']):
        os.symlink('/proc/self/fd/%d' % i, os.path.join(dev_path, dev))
    os.symlink('/proc/self/fd', os.path.join(dev_path, 'fd'))
    # Add extra devices
    DEVICES = {'null': (stat.S_IFCHR, 1, 3), 'zero': (stat.S_IFCHR, 1, 5),
               'random': (stat.S_IFCHR, 1, 8), 'urandom': (stat.S_IFCHR, 1, 9),
               'console': (stat.S_IFCHR, 136, 1), 'tty': (stat.S_IFCHR, 5, 0),
               'full': (stat.S_IFCHR, 1, 7)}
    for device, (dev_type, major, minor) in DEVICES.items():
        os.mknod(os.path.join(dev_path, device),
                 0o666 | dev_type, os.makedev(major, minor))


def contain(command, image_name, image_dir, container_id, container_dir):
     # TODO: time to say goodbye to the old mount namespace,
    #       see "man 2 unshare" to get some help
    #   HINT 1: there is no os.unshare(), time to use the linux module we made
    #           just for you!
    #   HINT 2: the linux module includes both functions and constants!
    #           e.g. linux.CLONE_NEWNS
    try:
        linux.unshare(linux.CLONE_NEWNS)  # create a new mount namespace
    except RuntimeError as e:
        if getattr(e, 'args', '') == (1, 'Operation not permitted'):
            print('Error: Use of CLONE_NEWNS with unshare(2) requires the '
                  'CAP_SYS_ADMIN capability (i.e. you probably want to retry '
                  'this with sudo)')
        raise e

    # new_root = create_container_root(image_name, image_dir, container_id, container_dir)
    # hardcoded as dont want to creat new container every time
    container_id = '62756d39-ddee-49b9-a2a8-3a3fbf4c8847' 
    new_root = f'workshop/containers/{container_id}/rootfs'
    print('Created a new root fs for our container: {}'.format(new_root))

   

    # TODO: remember shared subtrees?
    # (https://www.kernel.org/doc/Documentation/filesystems/sharedsubtree.txt)
    # Make / a private mount to avoid littering our host mount table.
    linux.mount(None, '/', None, linux.MS_PRIVATE | linux.MS_REC, None)


    # Create mounts (/proc, /sys, /dev) under new_root
    linux.mount('proc', os.path.join(new_root, 'proc'), 'proc', 0, '')
    # linux.mount('sysfs', os.path.join(new_root, 'sys'), 'sysfs', 0, '')
    linux.mount('tmpfs', os.path.join(new_root, 'dev'), 'tmpfs',
                linux.MS_NOSUID | linux.MS_STRICTATIME, 'mode=755')
    # Add some basic devices
    devpts_path = os.path.join(new_root, 'dev', 'pts')
    if not os.path.exists(devpts_path):
        os.makedirs(devpts_path)
        linux.mount('devpts', devpts_path, 'devpts', 0, '')
    

    # TODO: add more devices (e.g. null, zero, random, urandom) using os.mknod.
    makedev(os.path.join(new_root, 'dev'))

    os.chroot(new_root)

    os.chdir('/')

    os.execvp(command[0], command)


@cli.command(context_settings=dict(ignore_unknown_options=True,))
@click.option('--image-name', '-i', help='Image name', default='ubuntu')
@click.option('--image-dir', help='Images directory',
              default='workshop/images')
@click.option('--container-dir', help='Containers directory',
              default='workshop/containers')
@click.argument('Command', required=True, nargs=-1)
def run(image_name, image_dir, container_dir, command):
    container_id = str(uuid.uuid4())

    pid = os.fork()
    if pid == 0:
        # This is the child, we'll try to do some containment here
        try:
            contain(command, image_name, image_dir, container_id, container_dir)
        except Exception:
            traceback.print_exc()
            os._exit(1)  # something went wrong in contain()

    # This is the parent, pid contains the PID of the forked process
    # wait for the forked child, fetch the exit status
    _, status = os.waitpid(pid, 0)
    print('{} exited with status {}'.format(pid, status))


if __name__ == '__main__':
    cli()
