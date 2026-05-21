import mwclient

def test_wiki_fetch():
    # 1. 连接到 BiliGame Wiki
    # 注意：路径是 '/rocom/'
    print("正在连接到 wiki.biligame.com/rocom/...")
    site = mwclient.Site('wiki.biligame.com', path='/rocom/')

    # 2. 指定你要获取的页面标题
    page_title = '精灵图鉴'
    print(f"正在获取页面: {page_title}")
    page = site.pages[page_title]

    # 3. 检查页面是否存在
    if page.exists:
        # 4. 获取页面的维基源代码 (Wikitext)
        wikitext = page.text()
        print(f"✅ 成功获取页面 '{page_title}' 的内容")
        print(f"内容长度: {len(wikitext)} 字符")
        print("-" * 20)
        print("内容预览 (前 500 字符):")
        print(wikitext)
        print("-" * 20)
    else:
        print(f"❌ 页面 '{page_title}' 不存在。")

if __name__ == "__main__":
    try:
        test_wiki_fetch()
    except Exception as e:
        print(f"发生错误: {e}")
