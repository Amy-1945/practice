from datetime import date
from flask import Flask, abort, request, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5  # render form
from flask_ckeditor import CKEditor  # 用于编辑文字的大小，颜色，字体
from flask_gravatar import Gravatar  # 给每个用户添加头像
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user  # current_user在后面用得很多
from flask_sqlalchemy import SQLAlchemy
from functools import wraps  # 用来def admin_only
from werkzeug.security import generate_password_hash, check_password_hash  # 加密密码 + 对比密码
from sqlalchemy.orm import relationship  # 让一个tab(user)中的用户，可以和多个comments或者是blogs链接起来
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm  # 调用，另外一个单独的py文件
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
ckeditor = CKEditor(app)
Bootstrap5(app)

# 使用 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# 在这个db文件中，建立了2个独立的tab,分别存blog和user data
# 后来又增加了一个表格，comment，每增加一个表格，都需要删掉db文件，重新开始。
# 注意，删除的时候，所有3个tab的内容都会被删除，需要重新开始
# 删除的时候，不要选择safe。
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URL', "sqlite:///posts.db")
db = SQLAlchemy()
db.init_app(app)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)

    # Add child relationship
    # Create Foreign Key, "users.id" the users refers to the tablename of User.
    # 创建外键，“users.id”users指的是User的表名。
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # Create reference to the User object, the "posts" refers to the posts protperty in the User class.
    # 创建对 User 对象的引用，“posts”指的是 User 类中的 posts 属性。
    author = relationship("User", back_populates="posts")

    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    # author = db.Column(db.String(250), nullable=False) 在添加relationship之后，对这个进行更改
    img_url = db.Column(db.String(250), nullable=False)
    # Parent relationship to the comments
    comments = relationship("Comment", back_populates="parent_post")


# TODO: Create a User table for all your registered users. 
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))

    # 将一个author和多个posts，或者comments链接起来。Add parent relationship
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")


class Comment(db.Model):
    __tablename__ = "comments"  # 新的tab的名字
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)

    # Add child relationship to User
    # "users.id" The users refers to the tablename of the Users class.
    # "comments" refers to the comments property in the User class.
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")

    # Add child relationship to BlogPost
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()

#  给评论的用户，添加头像
gravatar = Gravatar(
    app,
    size=100,
    rating="g",
    default='retro',
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None
)


# 设置一些只有管理员才可以进行的操作，ID=1
def admin_only(f):
    @wraps(f)
    #  @wraps(f) 用于确保被装饰的函数 decorated_function 具有和原始函数 f 相同的名称、文档字符串等属性
    #  这是一个内部函数，它接受任意数量的位置参数 args 和关键字参数 kwargs。
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)  # 返回 HTTP 403 Forbidden 错误
        return f(*args, **kwargs)  # 如果用户是管理员，就调用原始的视图函数 f(*args, **kwargs)
    return decorated_function  # admin_only 装饰器返回了内部函数 decorated_function，
    # 这个函数包含了对用户权限的检查和原始视图函数的调用


@login_manager.user_loader
def load_user(user_id):
    # return User.query.get(user_id)
    return db.session.get(User, user_id)


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["POST", "GET"])
def register():
    form = RegisterForm()
    if request.method == "POST" and form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == request.form.get("email")))
        user = result.scalar()
        if user:
            flash("You have registered, please login")
            return redirect(url_for("login"))
        else:
            hashed_salted_password = generate_password_hash(request.form.get("password"),
                                                            method="pbkdf2:sha256",
                                                            salt_length=8)
            new_user = User(email=request.form.get("email"),
                            password=hashed_salted_password,
                            name=request.form.get("name")
                            )
            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)
            return redirect(url_for("get_all_posts"))

    return render_template("register.html",
                           current_user=current_user,
                           form=form)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        password = request.form.get("password")
        result = db.session.execute(db.select(User).where(User.email == request.form.get("email")))
        user = result.scalar()
        if not user:
            flash("The email does not exist, please try again")
            return redirect(url_for("login"))
        elif not check_password_hash(user.password, password):
            flash("Password incorrect, please try again")
            return redirect(url_for("login"))
        else:
            login_user(user)
            return redirect(url_for("get_all_posts"))

    return render_template("login.html", form=form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    # 使用post-ID从BlogPost调出post
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment")
            return redirect(url_for("login"))
        new_comment = Comment(
            text=comment_form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact")
def contact():
    return render_template("contact.html", current_user=current_user)


if __name__ == "__main__":
    app.run(debug=False, port=5002)
