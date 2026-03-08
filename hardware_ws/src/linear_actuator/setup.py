from setuptools import setup

package_name = 'linear_actuator'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rescue-pi',
    maintainer_email='rescue-pi@todo.todo',
    description='Linear actuator ROS2 node',
    license='TODO',
    entry_points={
        'console_scripts': [
            'linear_actuator = linear_actuator.linear_actuator:main',
        ],
    },
)
