import logging
import urllib
import urllib2
import hashlib
import time
import datetime

from google.appengine.api import mail
from google.appengine.ext import webapp, db
from google.appengine.api import urlfetch, memcache, users
from google.appengine.ext.webapp import util, template
from google.appengine.api.labs import taskqueue
from django.utils import simplejson
from django.template.defaultfilters import timesince

import tweepy
import datetime
from models import OAuthToken

class Twuser(db.Model):
    nickname = db.StringProperty(required=True)
    
class HackUp(db.Model):
    user = db.ReferenceProperty(Twuser)
    details = db.StringProperty(required=True, multiline=True)
    when = db.DateTimeProperty(auto_now_add=True)

class Confirm(db.Model):
    user = db.ReferenceProperty(Twuser)
    hackup = db.ReferenceProperty(HackUp)

class Comment(db.Model):
    user = db.ReferenceProperty(Twuser)
    hackup = db.ReferenceProperty(HackUp)
    text = db.StringProperty(required=True, multiline=True)

# Handlers:

class CommentHandler(webapp.RequestHandler):
    def post(self,id):
        
       twittername = self.request.cookies.get('username', '')
       user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
       idInt = 0
       try: 
         idInt = int(id)
         hackup = HackUp.get_by_id(idInt)
         if self.request.get("comment"):
           comment = Comment(
              user=user,
              hackup=hackup,
              text=self.request.get("comment")
           )
           comment.put()
         if (hackup):
           self.redirect('/view/' + id)
         else:
           self.redirect('/')
       except:
         self.redirect('/')


class ViewHandler(webapp.RequestHandler):
    def get(self,id):
       twittername = self.request.cookies.get('username', '')
       user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
       idInt = 0
       try: 
         idInt = int(id)
         hackup = HackUp.get_by_id(idInt)
         confirmList = Confirm.all().filter("hackup =", hackup)
         commentList = Comment.all().filter("hackup =", hackup)
         confirmed = Confirm.all().filter("hackup =", hackup).filter("user =", user).fetch(100)
         if (hackup):
           self.response.out.write(template.render('templates/view.html', locals()))
         else:
           self.redirect('/')
       except:
         self.redirect('/')

class CreateHandler(webapp.RequestHandler):
    def get(self):
       twittername = self.request.cookies.get('username', '')
       user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
       self.response.out.write(template.render('templates/create.html', locals()))
       
    def post(self):
       twittername = self.request.cookies.get('username', '')
       user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
       t = time.strptime(self.request.get("when"), "%d/%m/%Y")
       dt = datetime.datetime(*t[0:5])
       hackup = HackUp(user=user, details=self.request.get("descripcion","El fail user no escribio nada fail"), when=dt)
       hackup.put()
       self.redirect('/')

class ConfirmHandler(webapp.RequestHandler):
    def post(self, id):
       twittername = self.request.cookies.get('username', '')
       user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
       idInt = 0
       try:
         idInt = int(id)
         hackup = HackUp.get_by_id(idInt)
         confirm = Confirm.all().filter("hackup =", hackup).filter("user =", user).fetch(100)
         if(not confirm):
           confirm = Confirm(hackup=hackup, user=user)
           confirm.put()
         if (hackup and confirm):
           self.redirect('/view/' + id) 
         else:
           self.redirect('/')
       except:
         self.redirect('/')


CONSUMER_KEY = 'e9n31I0z64dagq3WbErGvA'
CONSUMER_SECRET = '9hwCupdAKV8EixeNdN3xrxL9RG3X3JTXI0Q520Oyolo'
CALLBACK = 'http://localhost:8086/callback'

class LoginHandler(webapp.RequestHandler):

    def get(self):
        # Build a new oauth handler and display authorization url to user.
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET, CALLBACK)
        try:
            self.response.out.write(template.render('templates/login.html', {
                    "authurl": auth.get_authorization_url(),
                    "request_token": auth.request_token
            }))
        except tweepy.TweepError, e:
            # Failed to get a request token
            print template.render('templates/error.html', {'message': e})
            return

        # We must store the request token for later use in the callback page.
        request_token = OAuthToken(
                token_key = auth.request_token.key,
                token_secret = auth.request_token.secret
        )
        request_token.put()


class CallbackHandler(webapp.RequestHandler):

    def get(self):
        oauth_token = self.request.get("oauth_token", None)
        oauth_verifier = self.request.get("oauth_verifier", None)
        if oauth_token is None:
            # Invalid request!
            print template.render('templates/error.html', {
                    'message': 'Missing required parameters!'
            })
            return

        # Lookup the request token
        request_token = OAuthToken.gql("WHERE token_key=:key", key=oauth_token).get()
        if request_token is None:
            # We do not seem to have this request token, show an error.
            print template.render('templates/error.html', {'message': 'Invalid token!'})
            return

        # Rebuild the auth handler
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        auth.set_request_token(request_token.token_key, request_token.token_secret)

        # Fetch the access token
        try:
            auth.get_access_token(oauth_verifier)
        except tweepy.TweepError, e:
            # Failed to get access token
            print template.render('templates/error.html', {'message': e})
            return

#COOKIE
        api = tweepy.API(auth)
        twittername = api.me().screen_name
        self.response.headers.add_header(
                'Set-Cookie', 
                'username=%s; expires=%s' \
                  % (twittername,  datetime.datetime.now().strftime("%a, %d-%m-%Y %H:%M:%S GMT")))

        user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
        if not user:
            user = Twuser(nickname= twittername)
            user.put()
            
        # So now we could use this auth handler.
        # Here we will just display the access token key&secret
        self.redirect('/')


class MainHandler(webapp.RequestHandler):
    def get(self):
        #user = users.get_current_user()
        twittername = self.request.cookies.get('username', '')
                
        if twittername:            
            logout_url = '/logout' #users.create_logout_url('/')
            user = Twuser.gql("WHERE nickname=:nickname", nickname=twittername).get()
        else:           
            login_url = '/login' #users.create_login_url('/')
            self.redirect(login_url)
        hackups = HackUp.all().filter("when >=", datetime.date.today() - datetime.timedelta(days=1)).order("when")
        self.response.out.write(template.render('templates/main.html', locals()))
    
class LogoutHandler(webapp.RequestHandler):
    def get(self):
        self.response.headers.add_header(
                'Set-Cookie', 
                'username=;' )
        self.redirect('/')

def main():
    application = webapp.WSGIApplication([
        ('/', MainHandler), #This list all the upcoming hackups and has a link to create a new one
        ('/view/(.+)', ViewHandler), #This allows to see details of the hackup, who is going, and confirm
        ('/confirm/(.+)', ConfirmHandler), #This allows to confirm going to a hackup
        ('/comment/(.+)', CommentHandler), #This allows to comment on the hackup
        ('/create', CreateHandler), #This allows to create a new thing
        ('/login', LoginHandler),
        ('/logout', LogoutHandler),
        ('/callback', CallbackHandler),
      ], debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
