"""Reader is a monadic wrapper around a function.
"""

from ..abc import Monad, Container
from ..utils import iscallable, _get_names
from ..funcs import const, compose


class Reader(Monad):
    r"""Monadic wrapper around a function. Compare to a Haskell implementation
    (where R is short for Reader):

        ..code-block: Haskell
        newtype R e a = R(e->a)

        runR :: R e a -> e -> a
        runR (R f) e = f e

        instance Functor (R e) where
            fmap f (R g) = R $ \e -> (f.g) e

        instance Applicative (R e) where
            pure x = R $ \_ -> x
            (R f) <*> (R g) = R $ \e -> (f e) (g e)

        instance Monad (R e) where
            return x = R $ \_ -> x
            r >>= g = R $ \e -> runR (g (runR r e)) e


    To understand the `>>=` definition, break it down as...

        ..code-block: Haskell
        (R f) >>= g = R $ \e -> runR (g (f e)) e
        --becomes
        (R f) >>= g = R $ \e -> let a = f e
                                in runR (g a) e
        --becomes
        (R f) >>= g = R $ \e -> let a = f e
                                    r = g a --type R b
                                in runR r e

    This monad allows passing an "execution environment" through a series
    of functions without having to do something like:

    >>> func1(env, func2(env, func3(env, x)))

    Instead you'd simply do:

    >>> r = Reader(func1)
    >>> s = r >> mfunc2 >> mfunc3

    Each function in the bind chain needs to return an instance of Reader
    when provided with an input:

    >>> def inc(x):
    ...     return x+1
    >>> def adder(x):
    ...     def add(y):
    ...         return x+y
    ...     return add
    >>> def madd(x):
    ...     return Reader(adder(x))
    >>> r = Reader(inc)
    >>> s = r >> madd >> madd
    >>> s(1)
    ... 4

    Of course, this is more useful when doing more than simply addition.

    >>> from operator import itemgetter
    >>> list_build = lambda x: lambda y: lambda z: [x,y,z]
    >>> # pynads provides a shortcut with R
    >>> a,b,c = R(itemgetter('a')), R(itemgetter('b')), R(itemgetter('c'))
    >>> env = {'a':10, 'b':7, 'c':9}
    >>> t = list_build % a * b * c
    >>> t(env)
    ... [10,7,9]
    """

    def __new__(cls, v):
        if not iscallable(v):
            raise TypeError("expected callable type to be passed")
        return Container.__new__(cls)

    def __call__(self, env):
        r"""In Haskell, Reader is defined like this:

            ..code-block: Haskell
            newtype Reader e a = Reader { runReader :: e-> a}
            -- or alternatively you can:
            newtype R e a = R (e->a)
            runR (R f) e = f e

        It's a thin wrapper around a function that accepts an input of type `e`
        and outputs a result of type `a`. `e` can be anything. The record
        syntax (the first definition) simply defines a "selector function" to
        easily extract the stored function, where as the second definition
        defines the extractor externally.

        Since the Reader monad is simply a wrapper around a function call,
        the easiest way to emulate this in Python to define `__call__` that
        accepts an input and runs the stored function with that input,
        returning the result to the caller.
        """
        return self.v(env)

    def __repr__(self):
        return "{}({!s})".format(*_get_names(self, self.v))

    @classmethod
    def unit(cls, v):
        r"""Compare to Haskell's implementation of `pure`/`return` for Reader:

            ..code-block: Haskell
            instance Applicative (Reader e) where
                pure x = Reader $ \_ -> x

        which generates a function that ignores input and returns its initial
        value. The initial value is a function. Meaning Reader.unit should
        accept a function.

        >>> def inc(x): return x+1
        >>> unit(inc, Reader)
        ... Reader: inc
        """
        return cls(const(v))

    def fmap(self, func):
        r"""Compare to Haskell's impelementation of fmap for Reader and (->)

            ..code-block: Haskell
            instance Functor ((->) r) where
                fmap f g = f . g
                -- or fmap = (.)

            instance Functor (Reader e) where
                fmap f (R g) = R $ \e -> (f . g) e

        This maps a function over the wrapped function.

        >>> def inc(x): return x+1
        >>> r = Reader(inc)
        >>> f = fmap(inc, r)
        >>> f(1)
        ... 3
        """
        return Reader(compose(func, self))

    def apply(self, applicative):
        r"""Compare to Haskell's applicative instance of Reader and (->)

            ..code-block: Haskell
            instance Applicative ((->) r) where
                pure x = \_ -> x
                f <*> g = \e -> (f e) (g e)

            instance Applicative (R e) where
                pure x = R $ \_ -> x
                (R f) <*> (R g) = R $ \e -> (f e) (g e)

        To shed some light on this, consider the following (from LYAH):

            ..code-block: Haskell
            (+) <$> (+3) <*> (*100) $ 5
            -- 508

            let f = (+)
            let g = (+3)
            let h = (*100)

            -- f <$> g means fmap f g means f.g
            let i = (+) . (+3)

            -- <*> composition of i and h
            let j = \e -> (i z) (h z)
            --      \e -> (((+) . (+3)) e) ((*100) e)

            -- feeding 5 through j ends up looking like this:
            -- j 5 = (((+) . (+3)) 5) ((*100) 5)
            -- j 5 = ((+) (5+3)) (5*100)
            -- j 5 = (+) 8 500
            -- j 5 = 8 + 500
            -- j 5 = 508

        Similarly, the Reader version of it resembles:

            ..code-block: Haskell
            let r = (+) <$> (R (+3)) <*> (R (*100))
            runR r 5
            -- 508

            let rf = (+)
            let rg = R (+3)
            let rh = R (*100)

            -- (+) <$> R (+3) means fmap (+) (R (+3))
            let ri = R (\e -> (+) . (+3) e)

            -- <*> composition of rh and ri
            let rj = R (\e -> (ri e) (rh e))
            -- Expand out what (ri e) and (rh e) really mean...
            --     = R (\e -> ((\f -> ((+) . (+3)) f) e) ((*100) e))
            -- Now simplify it by simulating feeding e into these functions
            --     = R (\e -> ((+) . (+3) e) ((*100) e))
            --     = R (\e -> (+) (e+3) (e*100)

            -- Run the whole thing!
            runR rj 5
            -- 508

        All of this serves to illustrate how to implement this in Python:

        >>> # poor man's currying
        >>> add = lambda x: lambda y: x+y
        >>> inc_3 = lambda x: x+3
        >>> mul_100 = lambda x: x*100
        >>> s = add % Reader(inc_three) * Reader(mul_100)
        >>> s(5) # compare: runR s 5
        ... 508

        Similarly, we can pull information from a dictionary as well:

        >>> from operator import itemgetter as read
        >>> t = add % Reader(read('a')) * Reader(read('b'))
        >>> t({'a':10, 'b':7})
        ... 17
        """
        # compare to:
        # let (R f) = rf
        #     (R g) = rg
        # in R $ \y -> (f y) (g y)
        def applied(env, f=self, g=applicative):
            r"""First supply the environment to this Reader to get a function
            back. And then call the returned function with the result of
            the function stored in the next applicative when provided with
            the same environment.
            """
            h = f(env)
            return h(g(env))

        names = _get_names(self.v, applicative.v)
        applied.__doc__ = "Application of {!s}".format(', '.join(names))
        applied.__name__ = '_o_'.join(names)

        return Reader(applied)

    def bind(self, bindee):
        r"""Compare to Haskell's implemention of Monad for Reader:

            ..code-block: Haskell
            instance Monad (R e) where
                return x = R $ \_ -> x
                r >>= g = R $ \e -> runR (g (runR r e)) e
            --and
            runR :: R e a -> e -> a
            runR (R f) e = f e

        To break down this a little more clearly:

            ..code-block: Haskell
            --make it clear there's two functions
            (R f) >>= g = R $ \e -> runR (g (f e)) e

            -- f e should return an a
            (R f) >>= g = R $ \e -> let a = f e
                                    in runR (g a) e

            -- g a should return an (R b)
            (R f) >>= g = R $ \e -> let a = f e
                                        r = g a
                                    in runR r e

            --it could also be broken down like this:
            r >>= g = R $ \e -> let a = runR r e
                                    s = g a
                                 in runR s e

        Keep in mind, this implementation of Reader utilizes Python's callable
        object protocol instead of defining an exterior function (runR).

        >>> inc = lambda x: x+1
        >>> minc = lambda x: Reader(lambda y: x+y+1))
        >>> s = R(inc) >> minc
        >>> s(1)
        ... 3

        To pull from an environment, you need to nest lambdas (yuck)
        where each nested lambda accepts the result of the former call
        and the final lambda preforms some sort of computation.
        Example taken from:
        <http://www.dustingetz.com/2012/10/02/reader-writer-state-monad-in-python.html>

        >>> from operator import itemgetter as read
        >>> computation = R(read('a')) >> (lambda a:
        ...               R(read('b')) >> (lambda b:
        ...               R.unit(a+b)             ))
        >>> computation({'a':10, 'b': 7})
        ... 17
        """
        def bound(env, f=self, g=bindee):
            r"""First run the function stored in this instance with the
            provided environment to get a result `a`. Feed that result to
            the function being bound to get a Reader instance. Finally,
            call the returned reader with the environment to get a result.
            """
            # compare to:
            # let a = runR r e
            #     s = g a
            # in runR s e
            a = f(env)
            r = g(a)
            return r(env)

        names = _get_names(self.v, bindee)
        bound.__doc__ = "Bind of {!s}".format(', '.join(names))
        bound.__name__ = '_x_'.join(names)

        return Reader(bound)


# since Reader is just a wrapper around a function
# it makes sense to alias it to Function as well
# though, it will still represent as Reader when introspected
Function = Reader
