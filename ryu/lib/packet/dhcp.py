# Copyright (C) 2013 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
DHCP packet parser/serializer

RFC 2131
DHCP packet format

    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |     op (1)    |   htype (1)   |   hlen (1)    |   hops (1)    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                            xid (4)                            |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |           secs (2)            |           flags (2)           |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                          ciaddr  (4)                          |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                          yiaddr  (4)                          |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                          siaddr  (4)                          |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                          giaddr  (4)                          |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                                                               |
    |                          chaddr  (16)                         |
    |                                                               |
    |                                                               |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                                                               |
    |                          sname   (64)                         |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                                                               |
    |                          file    (128)                        |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                                                               |
    |                          options (variable)                   |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

"""
import binascii
import random
import socket
import struct

from . import packet_base
from ryu.lib import stringify


DHCP_BOOT_REQUEST = 1
DHCP_BOOT_REPLY = 2

# DHCP message type code
DHCP_DISCOVER = 1
DHCP_OFFER = 2
DHCP_REQUEST = 3
DHCP_ACK = 5

# DHCP options tag code
DHCP_PAD_OPT = 0
DHCP_SUBNET_MASK_OPT = 1
DHCP_GATEWAY_ADDR_OPT = 3
DHCP_DNS_SERVER_ADDR_OPT = 6
DHCP_HOST_NAME_OPT = 12
DHCP_REQUESTED_IP_ADDR_OPT = 50
DHCP_IP_ADDR_LEASE_TIME_OPT = 51
DHCP_MESSAGE_TYPE_OPT = 53
DHCP_SERVER_IDENTIFIER_OPT = 54
DHCP_PARAMETER_REQUEST_LIST_OPT = 55
DHCP_RENEWAL_TIME_OPT = 58
DHCP_REBINDING_TIME_OPT = 59
DHCP_END_OPT = 255


class dhcp(packet_base.PacketBase):
    """DHCP (RFC 2131) header encoder/decoder class.

    The serialized packet would looks like the ones described
    in the following sections.

    * RFC 2131 DHCP packet format

    An instance has the following attributes at least.
    Most of them are same to the on-wire counterparts but in host byte order.
    __init__ takes the correspondig args in this order.

    .. tabularcolumns:: |l|L|

    ============== ====================
    Attribute      Description
    ============== ====================
    op             Message op code / message type.\
                   1 = BOOTREQUEST, 2 = BOOTREPLY
    htype          Hardware address type (e.g.  '1' = 10mb ethernet).
    hlen           Hardware address length (e.g.  '6' = 10mb ethernet).
    hops           Client sets to zero, optionally used by relay agent\
                   when booting via a relay agent.
    xid            Transaction ID, a random number chosen by the client,\
                   used by the client and serverto associate messages\
                   and responses between a client and a server.
    secs           Filled in by client, seconds elapsed since client\
                   began address acquisition or renewal process.
    flags          Flags.
    ciaddr         Client IP address; only filled in if client is in\
                   BOUND, RENEW or REBINDING state and can respond\
                   to ARP requests.
    yiaddr         'your' (client) IP address.
    siaddr         IP address of next server to use in bootstrap;\
                   returned in DHCPOFFER, DHCPACK by server.
    giaddr         Relay agent IP address, used in booting via a\
                   relay agent.
    chaddr         Client hardware address.
    sname          Optional server host name, null terminated string.
    boot_file      Boot file name, null terminated string; "generic"\
                   name or null in DHCPDISCOVER, fully qualified\
                   directory-path name in DHCPOFFER.
    options        Optional parameters field\
                   ('DHCP message type' option must be included in\
                    every DHCP message).
    ============== ====================
    """
    _HLEN_UNPACK_STR = '!BBB'
    _HLEN_UNPACK_LEN = struct.calcsize(_HLEN_UNPACK_STR)
    _DHCP_UNPACK_STR = '!BIHHIIII%ds%ds64s128s'
    _DHCP_PACK_STR = '!BBBBIHHIIII16s64s128s'
    _DHCP_CHADDR_LEN = 16
    _HARDWARE_TYPE_ETHERNET = 1

    def __init__(self, op, chaddr, options, htype=_HARDWARE_TYPE_ETHERNET,
                 hlen=0, hops=0, xid=None, secs=0, flags=0, ciaddr=0, yiaddr=0,
                 siaddr=0, giaddr=0, sname='', boot_file=''):
        super(dhcp, self).__init__()
        self.op = op
        self.htype = htype
        if hlen == 0:
            self.hlen = len(chaddr)
        else:
            self.hlen = hlen
        self.hops = hops
        if xid is None:
            self.xid = random.randint(0, 0xffffffff)
        else:
            self.xid = xid
        self.secs = secs
        self.flags = flags
        self.ciaddr = ciaddr
        self.yiaddr = yiaddr
        self.siaddr = siaddr
        self.giaddr = giaddr
        self.chaddr = chaddr
        self.sname = sname
        self.boot_file = boot_file
        self.options = options

    @classmethod
    def parser(cls, buf):
        (op, htype, hlen) = struct.unpack_from(cls._HLEN_UNPACK_STR, buf)
        buf = buf[cls._HLEN_UNPACK_LEN:]
        unpack_str = cls._DHCP_UNPACK_STR % (hlen,
                                             (cls._DHCP_CHADDR_LEN - hlen))
        min_len = struct.calcsize(unpack_str)
        (hops, xid, secs, flags, ciaddr, yiaddr, siaddr, giaddr, chaddr,
         dummy, sname, boot_file
         ) = struct.unpack_from(unpack_str, buf)
        length = min_len
        if len(buf) > min_len:
            parse_opt = options.parser(buf[min_len:])
            length += parse_opt.options_len
        return (cls(op, chaddr, parse_opt, htype, hlen, hops, xid, secs, flags,
                    ciaddr, yiaddr, siaddr, giaddr, sname, boot_file),
                None, buf[length:])

    def serialize(self, payload, prev):
        seri_opt = self.options.serialize()
        pack_str = '%s%ds' % (self._DHCP_PACK_STR,
                              self.options.options_len)
        return struct.pack(pack_str, self.op, self.htype, self.hlen,
                           self.hops, self.xid, self.secs, self.flags,
                           self.ciaddr, self.yiaddr, self.siaddr, self.giaddr,
                           self.chaddr, self.sname, self.boot_file, seri_opt)


class options(stringify.StringifyMixin):
    """DHCP (RFC 2132) options encoder/decoder class.

    This is used with ryu.lib.packet.dhcp.dhcp.

    An instance has the following attributes at least.
    Most of them are same to the on-wire counterparts but in host byte order.
    __init__ takes the correspondig args in this order.

    .. tabularcolumns:: |l|L|

    ============== ====================
    Attribute      Description
    ============== ====================
    option_list    'end option' and 'pad option' are added automatically\
                   after the option class is stored in array.
    options_len    Option's byte length.\
                   ('magic cookie', 'end option' and 'pad option'\
                    length including.)
    magic_cookie   The first four octets contain the decimal values\
                   99, 130, 83 and 99.
    ============== ====================
    """
    _MAGIC_COOKIE_UNPACK_STR = '!I'
    # same magic cookie as is defined in RFC 1497
    _MAGIC_COOKIE = socket.inet_aton("99.130.83.99")
    _OPT_TAG_LEN_BYTE = 2

    def __init__(self, option_list=None, options_len=0,
                 magic_cookie=_MAGIC_COOKIE):
        super(options, self).__init__()
        if option_list is None:
            self.option_list = []
        else:
            self.option_list = option_list
        self.options_len = options_len
        self.magic_cookie = magic_cookie

    @classmethod
    def parser(cls, buf):
        opt_parse_list = []
        offset = struct.calcsize(cls._MAGIC_COOKIE_UNPACK_STR)
        magic_cookie = struct.unpack_from(cls._MAGIC_COOKIE_UNPACK_STR, buf)[0]
        while len(buf) > offset:
            opt_buf = buf[offset:]
            opt = option.parser(opt_buf)
            if opt is None:
                break
            opt_parse_list.append(opt)
            offset += opt.length + cls._OPT_TAG_LEN_BYTE
        return cls(opt_parse_list, len(buf), magic_cookie)

    def serialize(self):
        seri_opt = self.magic_cookie
        for opt in self.option_list:
            seri_opt += opt.serialize()
        seri_opt += binascii.a2b_hex('%x' % DHCP_END_OPT)
        if self.options_len == 0:
            self.options_len = len(seri_opt)
        return seri_opt


class option(stringify.StringifyMixin):
    """DHCP (RFC 2132) options encoder/decoder class.

    This is used with ryu.lib.packet.dhcp.dhcp.options.

    An instance has the following attributes at least.
    Most of them are same to the on-wire counterparts but in host byte order.
    __init__ takes the correspondig args in this order.

    ============== ====================
    Attribute      Description
    ============== ====================
    tag            Option type.\
                   (except for the 'magic cookie', 'pad option'\
                    and 'end option'.)
    value          Option's value.\
                   (set the value that has been converted to hexadecimal.)
    length         Option's value length.\
                   (calculated automatically from the length of value.)
    ============== ====================
    """
    _UNPACK_STR = '!B'
    _MIN_LEN = struct.calcsize(_UNPACK_STR)

    def __init__(self, tag, value, length=0):
        super(option, self).__init__()
        self.tag = tag
        self.value = value
        self.length = length

    @classmethod
    def parser(cls, buf):
        tag = struct.unpack_from(cls._UNPACK_STR, buf)[0]
        if tag == DHCP_END_OPT or tag == DHCP_PAD_OPT:
            return None
        buf = buf[cls._MIN_LEN:]
        length = struct.unpack_from(cls._UNPACK_STR, buf)[0]
        buf = buf[cls._MIN_LEN:]
        value_unpack_str = '%ds' % length
        value = struct.unpack_from(value_unpack_str, buf)[0]
        return cls(tag, value, length)

    def serialize(self):
        if self.length == 0:
            self.length = len(self.value)
        options_pack_str = '!BB%ds' % self.length
        return struct.pack(options_pack_str, self.tag, self.length, self.value)
