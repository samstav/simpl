# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Constants used across modules."""

# This is the key of the default key-pair that every deployment should have.
DEFAULT_KEYPAIR = 'deployment-keys'

# Used when parsing or simulating so keys don't have to be generated
DUMMY_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAoJ/A7ofO0KlB2KVvyhfFDuadBwCUrUYgB5ROSCYSsMVxNmQr
hiFcoMsj34k6MkihL/TUyGJTu0tGbLdgXaPZFZDNkb9odPomDOImcrHSAiYLBN04
Svoz/wldjYP5p8rdLqQYmOpSq4RiSJ2BCLSTJrrBJN+UQvisfB0cbLN8fqbvYHtc
Z9VN8W2raDhDXTSAIlTQphQwkJB/xXOqZfJsj/Zk3R9osJu9RzM30vFA+2xcahtj
gZBiUiP4dOKQkIGPOj+J+n10iU1Pn1PoQmWMIfzfx++J9oCWBOJc4yR9PC+xwco5
3LnqNVjqsldaYn09xwvzCq8lepnwjbie9Yc0twIDAQABAoIBAFwmqwpuMdH2eQdx
CmyYLH77AXXF+IZcZ/3RMQQli62M6QG6gFnog/rf8InLce7tSkR4Iyd/eehHLHUs
04WFfgLoW3fVp3kNFo1npYVBzWlcKBA3Vpd1aiVUWy7YW3/PXAvpKw93x8wNHFHq
wt+asZ2ToUGlX6r4fgSKswcOBkumUpZckwV6zpmz5mHdXfE1dh5LYm+tODSaGoqK
O9Q1pqGlC8JvIjtwwglCsqk3ZrXc3hwgyYdifpwx8BMb2rZa8dYON1SEH8PAjZyZ
6k0paUemF7YT78/o9AXbSMnfLud0js+hO6p/lIqXCMXERdbspLq8bcOI3kn/uTt0
g1PkDkECgYEAuKNp8tjtyC6zHE6ZlK4mHFT1Wlir4eufM/BLpABvqSDrz9tRQRZC
xc/qCuWpfdzSzRKDQZascNC4ly+bDtFXSH1m/pttCkTrgXocimozQPElfrugCtzL
xkbfOsn5ADQ+HFbL0JTiPMqp3Sc7hq18KVJ0a82/SoGukB4lU6KY1FcCgYEA3rRN
23eerP7kzK3y67oD9OrkV6Yzsn63aiB+/WmwJPkadseuIrzTqbCtmPDHkZIlblql
L+UFajnLi0ln518xMVFJ4tZuVs8INsl/5nXcSIc2vvkLWVqkc1649jOdcm6vBuIt
/QY2OrydnQY5IKFbnFH+8Sy6WpargLbyII5JZqECgYEAmfR4hWvoaUC3TGUlnlnP
oVQd+SVyvMBxUSeOisNqV8YBmqGvEOx05OhGqKtzNmWIyEIle+0dADypjja9vg9E
DkeyN551v1hUXvPpFGkVL5NjxlbATg5pQ30Y6bY7j7YADDU7YUKjmjkKhkMOWXAS
1YnRVYqLdJ7JZZYdXa14baUCgYEA0odcerZQOHYV0TA3zoPgra1IA1vIz1pfBWKG
6gT5UVpznAoUIh6jcWzmDwi/gGvKGtJyCh7UyaCtPJU+NkmU9WxFDr1rPYEl4LUH
xdNxVNcN9+byxZucjrvi2kvc8YqUx0sV8nXm2gvoa8KwSpp/Qf15poCEApMgueM4
bXJVDUECgYAn+ZU4aNdKW1eVKB8cRX13Y3oaP9k4XSKci/XjCc+KqPvnVkcbt+J1
OxK9cb/HUIOOJwaLKymrlxCddZjrrFwSGYdpHn19KM+nUlbgTSKOYEs32vuNbd/a
0tfYsyBZitpdG5/WkQnRrWeCiGFMbFbDfcS3t1+Pb5xial8A5EbySQ==
-----END RSA PRIVATE KEY-----"""

DUMMY_PUBLIC_KEY = """"-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoJ/A7ofO0KlB2KVvyhfF
DuadBwCUrUYgB5ROSCYSsMVxNmQrhiFcoMsj34k6MkihL/TUyGJTu0tGbLdgXaPZ
FZDNkb9odPomDOImcrHSAiYLBN04Svoz/wldjYP5p8rdLqQYmOpSq4RiSJ2BCLST
JrrBJN+UQvisfB0cbLN8fqbvYHtcZ9VN8W2raDhDXTSAIlTQphQwkJB/xXOqZfJs
j/Zk3R9osJu9RzM30vFA+2xcahtjgZBiUiP4dOKQkIGPOj+J+n10iU1Pn1PoQmWM
Ifzfx++J9oCWBOJc4yR9PC+xwco53LnqNVjqsldaYn09xwvzCq8lepnwjbie9Yc0
twIDAQAB\n-----END PUBLIC KEY-----"""

DUMMY_PUBLIC_KEY_SSH = """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCgn8Duh87QqUHYpW/K\
F8UO5p0HAJStRiAHlE5IJhKwxXE2ZCuGIVygyyPfiToySKEv9NTIYlO7S0Zst2Bdo9kVkM2Rv2h0+i\
YM4iZysdICJgsE3ThK+jP/CV2Ng/mnyt0upBiY6lKrhGJInYEItJMmusEk35RC+Kx8HRxss3x+pu9g\
e1xn1U3xbatoOENdNIAiVNCmFDCQkH/Fc6pl8myP9mTdH2iwm71HMzfS8UD7bFxqG2OBkGJSI/h04p\
CQgY86P4n6fXSJTU+fU+hCZYwh/N/H74n2gJYE4lzjJH08L7HByjncueo1WOqyV1pifT3HC/MKryV6\
mfCNuJ71hzS3"""
