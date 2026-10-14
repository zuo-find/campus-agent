"""打印本机局域网 IP —— 真机 / 体验版调试时，小程序要连的就是这个地址。

只建一个 UDP socket 取出口网卡地址，不会真的发包，也不需要联网。
拿不到时回退 127.0.0.1（说明当前没有可用的局域网连接）。
"""
import socket


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))     # 只用于选出网卡，UDP 不会真的握手
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    print(lan_ip())
