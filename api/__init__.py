"""api —— 接口层。

这一层把「URL + 参数」包装成「有名字的方法」：
    client.post("/api/account/login", json={...})   ← 基础层写法，看不出业务
    account_api.login("alice", "pw123")             ← 接口层写法，一眼看懂在干什么

好处：接口路径变了、参数名改了，只改这一个文件，用例不用动。
"""
