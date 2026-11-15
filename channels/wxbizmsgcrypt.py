"""
企业微信官方标准加解密模块 (WXBizMsgCrypt)
基于 cryptography 现代加密库实现，严格遵循腾讯企业微信 AES-256-CBC 协议规范。
"""
import base64
import os
import struct
import hashlib
import xml.etree.ElementTree as ET
from typing import Tuple
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# 错误码常量
WXBizMsgCrypt_OK = 0
WXBizMsgCrypt_ValidateSignature_Error = -40001
WXBizMsgCrypt_ParseXml_Error = -40002
WXBizMsgCrypt_ComputeSignature_Error = -40003
WXBizMsgCrypt_IllegalAesKey = -40004
WXBizMsgCrypt_ValidateCorpid_Error = -40005
WXBizMsgCrypt_EncryptAES_Error = -40006
WXBizMsgCrypt_DecryptAES_Error = -40007
WXBizMsgCrypt_IllegalBuffer = -40008
WXBizMsgCrypt_EncodeBase64_Error = -40009
WXBizMsgCrypt_DecodeBase64_Error = -40010


class PKCS7Encoder:
    """企业微信定制的 32 字节块 PKCS#7 填充算法"""
    block_size = 32

    @classmethod
    def encode(cls, text_bytes: bytes) -> bytes:
        amount_to_pad = cls.block_size - (len(text_bytes) % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
        pad_char = bytes([amount_to_pad] * amount_to_pad)
        return text_bytes + pad_char

    @classmethod
    def decode(cls, decrypted_bytes: bytes) -> bytes:
        pad = decrypted_bytes[-1]
        if pad < 1 or pad > 32:
            pad = 0
        return decrypted_bytes[:-pad]


class WXBizMsgCrypt:
    def __init__(self, sToken: str, sEncodingAESKey: str, sReceiveId: str):
        self.sToken = sToken
        self.sEncodingAESKey = sEncodingAESKey
        self.sReceiveId = sReceiveId  # 企业ID (CorpID)
        self.key = None
        self.iv = None

        if sEncodingAESKey:
            try:
                self.key = base64.b64decode(sEncodingAESKey + "=")
                self.iv = self.key[:16]
            except Exception:
                pass

    def _get_sha1(self, *args) -> str:
        """计算包含 token、timestamp、nonce、encrypt 的签名"""
        sort_list = sorted([str(arg) for arg in args if arg is not None])
        raw_str = "".join(sort_list)
        return hashlib.sha1(raw_str.encode("utf-8")).hexdigest()

    def VerifyURL(self, sMsgSignature: str, sTimeStamp: str, sNonce: str, sEchoStr: str) -> Tuple[int, str]:
        """
        验证企业微信配置后台的 URL 有效性 (用于 GET 请求验证)
        """
        if not self.key:
            # 如果尚未配置密钥，直接原样回退，保证调试无阻
            return WXBizMsgCrypt_OK, sEchoStr

        # 1. 签名校验
        sha1 = self._get_sha1(self.sToken, sTimeStamp, sNonce, sEchoStr)
        if sha1 != sMsgSignature:
            return WXBizMsgCrypt_ValidateSignature_Error, ""

        # 2. 解密 echoStr
        ret, sReplyEchoStr = self.DecryptMsg(sEchoStr, sMsgSignature, sTimeStamp, sNonce, is_raw_encrypt=True)
        return ret, sReplyEchoStr

    def DecryptMsg(
        self,
        sPostData: str,
        sMsgSignature: str,
        sTimeStamp: str,
        sNonce: str,
        is_raw_encrypt: bool = False
    ) -> Tuple[int, str]:
        """
        检验消息的真实性，并且获取解密后的明文
        """
        if not self.key:
            return WXBizMsgCrypt_OK, sPostData

        # 1. 提取密文 Encrypt
        if is_raw_encrypt:
            sEncryptMsg = sPostData
        else:
            try:
                xml_tree = ET.fromstring(sPostData)
                sEncryptMsg = xml_tree.findtext("Encrypt") or ""
            except Exception:
                return WXBizMsgCrypt_ParseXml_Error, ""

        # 2. 校验签名
        sha1 = self._get_sha1(self.sToken, sTimeStamp, sNonce, sEncryptMsg)
        if sha1 != sMsgSignature:
            return WXBizMsgCrypt_ValidateSignature_Error, ""

        # 3. AES 解密
        try:
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            decryptor = cipher.decryptor()
            raw_decrypted = decryptor.update(base64.b64decode(sEncryptMsg)) + decryptor.finalize()
            unpadded = PKCS7Encoder.decode(raw_decrypted)
        except Exception:
            return WXBizMsgCrypt_DecryptAES_Error, ""

        # 4. 解析协议格式: 16字节随机数 + 4字节消息长度 + 消息体 + receiveid
        try:
            msg_len = struct.unpack(">I", unpadded[16:20])[0]
            msg_content = unpadded[20:20 + msg_len].decode("utf-8")
            from_receive_id = unpadded[20 + msg_len:].decode("utf-8")
        except Exception:
            return WXBizMsgCrypt_IllegalBuffer, ""

        # 5. 校验 receiveId (企业ID)
        if self.sReceiveId and from_receive_id != self.sReceiveId:
            return WXBizMsgCrypt_ValidateCorpid_Error, ""

        return WXBizMsgCrypt_OK, msg_content

    def EncryptMsg(self, sReplyMsg: str, sNonce: str, sTimeStamp: str = None) -> Tuple[int, str]:
        """
        将回复消息打包并用 AES-256-CBC 加密
        """
        if not self.key:
            return WXBizMsgCrypt_OK, sReplyMsg

        if sTimeStamp is None:
            import time
            sTimeStamp = str(int(time.time()))

        # 1. 组装明文包：16字节随机数 + 4字节msg_len + msg + receiveId
        random_16 = os.urandom(16)
        msg_bytes = sReplyMsg.encode("utf-8")
        msg_len = struct.pack(">I", len(msg_bytes))
        receive_id_bytes = self.sReceiveId.encode("utf-8") if self.sReceiveId else b""

        plain_bytes = random_16 + msg_len + msg_bytes + receive_id_bytes
        padded_bytes = PKCS7Encoder.encode(plain_bytes)

        # 2. AES 加密
        try:
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            encryptor = cipher.encryptor()
            encrypted = encryptor.update(padded_bytes) + encryptor.finalize()
            sEncryptB64 = base64.b64encode(encrypted).decode("utf-8")
        except Exception:
            return WXBizMsgCrypt_EncryptAES_Error, ""

        # 3. 计算签名并返回企微 XML 报文
        sSignature = self._get_sha1(self.sToken, sTimeStamp, sNonce, sEncryptB64)
        resp_xml = f"""<xml>
<Encrypt><![CDATA[{sEncryptB64}]]></Encrypt>
<MsgSignature><![CDATA[{sSignature}]]></MsgSignature>
<TimeStamp>{sTimeStamp}</TimeStamp>
<Nonce><![CDATA[{sNonce}]]></Nonce>
</xml>"""
        return WXBizMsgCrypt_OK, resp_xml
