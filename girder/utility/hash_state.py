#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright 2013 Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

# Utility for saving and restoring the internal state of a hash object
# so that checksums can be streamed without having to remain in memory.
# Inspired by http://code.activestate.com/recipes/
# 578479-save-and-restore-sha-512-internal-state/

import hashlib
import ctypes
import binascii


def _getHashStateDataPointer(hashObject):
    """
    Get a pointer to the internal hash state of a hash object.

    :param hashObject: A hashlib hash object.
    :return: A ctypes pointer to the internal hash state.
    :rtype: ctypes.POINTER(ctypes.c_char)
    """
    # From
    #   * github.com/python/cpython/blob/2.7/Modules/_hashopenssl.c#L58
    # the layout of a hashObject (_hashlib.HASH) is:
    #     typedef struct {
    #         PyObject_HEAD
    #         PyObject *name;
    #         EVP_MD_CTX ctx;
    #         ...
    #     } EVPobject;
    #
    # Using
    #   * docs.python.org/2/c-api/structures.html#c.PyObject_HEAD
    #   * github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/evp/evp.h#L265
    # this expands to:
    #     typedef struct {
    #         Py_ssize_t ob_refcnt;      // Word 0
    #         PyTypeObject *ob_type;     // Word 1
    #         PyObject *name;            // Word 2
    #         struct env_md_ctx_st {
    #             const EVP_MD *digest;  // Word 3
    #             ENGINE *engine;        // Word 4
    #             unsigned long flags;   // Word 5
    #             void *md_data;         // Word 6
    #             ...
    #         } /* EVP_MD_CTX */;
    #         ...
    #     } EVPobject;
    #
    # Thus, an offset of 6 words ( sizeof(void*) is 1 word) is required
    STATE_POINTER_OFFSET = 6

    hashPointer = ctypes.cast(id(hashObject), ctypes.POINTER(ctypes.c_void_p))
    statePointer = hashPointer[STATE_POINTER_OFFSET]
    stateDataPointer = ctypes.cast(statePointer, ctypes.POINTER(ctypes.c_char))
    assert stateDataPointer
    return stateDataPointer


_HASH_INFOS = dict()


class _HashInfo(object):
    def __init__(self, type, stateSize, initVectorFirstWord):
        self.type = type
        self.stateSize = stateSize

        # Instantiate to get the name and do a sanity check
        instance = self.type()
        self.name = instance.name

        stateDataPointer = _getHashStateDataPointer(instance)
        assert stateDataPointer[:8] == initVectorFirstWord

        _HASH_INFOS[self.name] = self


_HashInfo(
    type=hashlib.md5,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/md5/md5.h#L100
    stateSize=92,
    # Found empirically
    initVectorFirstWord=b'\x01\x23\x45\x67\x89\xab\xcd\xef'
)
_HashInfo(
    type=hashlib.sha1,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha.h#L100
    stateSize=96,
    # Found empirically
    initVectorFirstWord=b'\x01\x23\x45\x67\x89\xab\xcd\xef'
)
_HashInfo(
    type=hashlib.sha224,
    # Uses the same struct as sha256
    stateSize=112,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha256.c#L22
    initVectorFirstWord=b'\xd8\x9e\x05\xc1\x07\xd5\x7c\x36'
)
_HashInfo(
    type=hashlib.sha256,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha.h#L135
    stateSize=112,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha256.c#L33
    initVectorFirstWord=b'\x67\xe6\x09\x6a\x85\xae\x67\xbb'
)
_HashInfo(
    type=hashlib.sha384,
    # Uses the same struct as sha512
    stateSize=216,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha512.c#L64
    initVectorFirstWord=b'\xd8\x9e\x05\xc1\x5d\x9d\xbb\xcb'
)
_HashInfo(
    type=hashlib.sha512,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha.h#L182
    stateSize=216,
    # github.com/openssl/openssl/blob/OpenSSL_1_0_1f/crypto/sha/sha512.c#L80
    initVectorFirstWord=b'\x08\xc9\xbc\xf3\x67\xe6\x09\x6a'
)


def serialize(hashObject):
    """
    Serializes the internal state of the hash object passed in. Calling
    restore() on the serialized value afterward will return an equivalent
    hash object to the one passed.

    :param hashObject: The hash object to serialize.
    :type hashObject: _hashlib.HASH
    :returns: A binary string representing the serialized state.
    """
    stateDataPointer = _getHashStateDataPointer(hashObject)
    hashInfo = _HASH_INFOS[hashObject.name]
    return stateDataPointer[:hashInfo.stateSize]


def restore(oldStateData, hashName):
    """
    Unserializes a hash object from a binary string created by the
    serialize() method in this module.

    :param oldStateData: The serialized state.
    :type oldStateData: binary string
    :param hashName: The name of the hash algorithm type.
    :type hashName: str
    :returns: A hash object in the same state as the one that serialize()
              was called on.
    """
    hashInfo = _HASH_INFOS[hashName]
    assert len(oldStateData) == hashInfo.stateSize

    hashObject = hashInfo.type()
    stateDataPointer = _getHashStateDataPointer(hashObject)

    for i, byte in enumerate(oldStateData):
        stateDataPointer[i] = byte

    return hashObject


def serializeHex(hashObject):
    return binascii.b2a_hex(serialize(hashObject))


def restoreHex(oldHexStateData, hashName):
    return restore(binascii.a2b_hex(oldHexStateData), hashName)
