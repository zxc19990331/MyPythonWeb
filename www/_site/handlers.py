#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''

__author__ = 'Engine'

import time
import re
import json
import logging
import hashlib
import base64
import asyncio
import markdown2
from aiohttp import web
from coroweb import get, post # 导入装饰器,这样就能很方便的生成request handler
from models import User, Comment, Blog, next_id
from apis import APIResourceNotFoundError, APIValueError
from config import configs


# 此处所列所有的handler都会在app.py中通过add_routes自动注册到app.router上
# 因此,在此脚本尽情地书写request handler即可

_RE_EMAIL = re.compile(r'^[a-zA-Z0-9\.\-\_]+\@[a-zA-Z0-9\-\_]+(.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'[0-9a-f]{40}$')
COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret

def user2cookie(user, max_age):
    '''Generate cookie str by user.'''
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = "%s-%s-%s-%s" % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode("utf-8")).hexdigest()]
    reutrn "-".join(L)

@asyncio.coroutine
def cookie2user(cookie_str):
    '''Parse cookie and load user if cookie is valid'''
    if not cookie_str:
        return None
    try:
        L = cookie_str.split("-")
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = yield from User.find(uid)
        if user is None:
            return None
        s = "%s-%s-%s-%s" % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode("utf-8")).hexdigest():
            logging.info("invalid sha1")
            return None
        user.passwd = "*****"
        return user
    except Exception as e:
        logging.exception(e)
    return None


# 对于首页的get请求的处理
@get('/')
def index(request):
    # summary用于在博客首页上显示的句子,这样真的更有feel
    summary = "Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
    # 这里只是手动写了blogs的list, 并没有真的将其存入数据库
    blogs = [
        Blog(id="1", name="Test1 Blog", summary=summary, created_at=time.time()-120),
        Blog(id="2", name="Test2 Blog", summary=summary, created_at=time.time()-3600),
        Blog(id="3", name="Test3 Blog", summary=summary, created_at=time.time()-7200)
    ]
    # 返回一个字典, 其指示了使用何种模板,模板的内容
    # app.py的response_factory将会对handler的返回值进行分类处理
    return {
        "__template__": "blogs.html",
        "blogs": blogs
    }

@get("/register")
def register():
    return{
        "__template__": "register.html"
    }

@get("/signin")
def signin():
    return{
        "__template__": "signin.html"
    }

@get('/api/users')
def api_get_users():
    users = yield from User.findAll(orderBy="created_at desc")
    for u in users:
        u.passwd = "*****"
    # 以dict形式返回,并且未指定__template__,将被app.py的response factory处理为json
    return dict(users=users)

@post("/api/authenticate")
def authenticate(*, email, passwd):
    if not email:
        raise APIValueError("email", "Invalid email")
    if not passwd:
        raise APIValueError("passwd", "Invalid password")
    users = yield from User.findAll("email=?", [email])
    # check passwd:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode("utf-8"))
    sha1.update(b":")
    sha1.update(passwd.encode("utf-8"))
    if user.passwd != sha1.hexdigest():
        raise APIValueError("passwd", "Invalid password")
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = "*****"
    r.content_type = "application/json"
    r.body = json.dump(user, ensure_ascii=False).encode("utf-8")
    return r

@get("/signout")
def signout(request):
    referer = request.headers.get("Referer")
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, "-deleted-", max_age=0, httponly=True)
    logging.info("user signed out.")
    return r

@post('/api/users')
def api_register_user(*,email, name, passwd):
    if not name or not name.strip():
        raise APIValueError("name")
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError("email")
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError("passwd")
    users = yield from User.findAll('email=?', [email]) # mysql parameters are listed in list
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image="http://www.gravatar.com/avatar/%s?d=mm&s=120" % hashlib.md5(email.encode('utf-8')).hexdigest())
    yield from user.save()
    # make session cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '*****'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

