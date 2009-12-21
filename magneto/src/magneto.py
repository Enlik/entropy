#!/usr/bin/python2 -O
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Updates Notification Applet (Magneto) startup application}

"""
import os
import sys
#import signal
sys.path.insert(0, '/usr/lib/entropy/client')
sys.path.insert(0, '/usr/lib/entropy/libraries')
sys.path.insert(0, '/usr/lib/entropy/sulfur')
sys.path.insert(0, '../../client')
sys.path.insert(0, '../../libraries')
sys.path.insert(0, '../../sulfur/src')
sys.path.insert(0, '../')
sys.argv.append('--no-pid-handling')

kde_env = os.getenv("KDE_FULL_SESSION")

if "--kde" in sys.argv:
    from magneto.kde.interfaces import Magneto
elif "--gtk" in sys.argv:
    from magneto.gtk.interfaces import Magneto
else:
    if kde_env is not None:
        # this is KDE!
        try:
            from magneto.kde.interfaces import Magneto
        except ImportError:
            # try GTK
            from magneto.gtk.interfaces import Magneto
    else:
        # load GTK
        from magneto.gtk.interfaces import Magneto

if __name__ == "__main__":
    magneto = Magneto()
    try:
        magneto.startup()
        magneto.close_service()
    except KeyboardInterrupt:
        try:
            magneto.close_service()
        except:
            pass
        raise
    raise SystemExit(0)

