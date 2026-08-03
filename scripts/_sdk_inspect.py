# exact auth call signature + default host
import inspect

from kalshi_python import ApiClient, Configuration

print("set_kalshi_auth:", str(inspect.signature(ApiClient.set_kalshi_auth)))
import kalshi_python.api_client as ac

src = inspect.getsource(ac)
i = src.find("def set_kalshi_auth")
print(src[i:i+600])
print("default host:", Configuration().host)
