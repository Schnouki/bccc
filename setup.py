# Copyright 2012 Thomas Jost
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software stributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

from setuptools import setup, find_packages

version = "0.0.1"

setup(name="bccc",
      version=version,
      description="buddycloud console client",
      author="Thomas Jost",
      author_email="schnouki@schnouki.net",
      license="Apache License, version 2.0",
      url="https://github.com/Schnouki/bccc",

      packages=find_packages(),
      scripts=["bin/bccc"],
      include_package_data=True,

      setup_requires=["distribute"],
      install_requires=[
          "distribute",
          "python-dateutil",
          "sleekxmpp >= 1.1.10",
          "urwid >= 1.0.1",
      ],
      extras_require={
          "DNS": ["dnspython3"],
      }
)

# Local Variables:
# mode: python3
# End:
