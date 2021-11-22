#!/usr/bin/env python3

import email.mime.text
import email.utils
import smtplib
import subprocess
import sys
import textwrap

import aurweb.config
import aurweb.db
import aurweb.l10n

aur_location = aurweb.config.get('options', 'aur_location')


def headers_msgid(thread_id):
    return {'Message-ID': thread_id}


def headers_reply(thread_id):
    return {'In-Reply-To': thread_id, 'References': thread_id}


def username_from_id(conn, uid):
    cur = conn.execute('SELECT UserName FROM Users WHERE ID = ?', [uid])
    return cur.fetchone()[0]


def pkgbase_from_id(conn, pkgbase_id):
    cur = conn.execute('SELECT Name FROM PackageBases WHERE ID = ?',
                       [pkgbase_id])
    return cur.fetchone()[0]


def pkgbase_from_pkgreq(conn, reqid):
    cur = conn.execute('SELECT PackageBaseID FROM PackageRequests ' +
                       'WHERE ID = ?', [reqid])
    return cur.fetchone()[0]


class Notification:
    def get_refs(self):
        return ()

    def get_headers(self):
        return {}

    def get_cc(self):
        return []

    def get_body_fmt(self, lang):
        body = ''
        for line in self.get_body(lang).splitlines():
            if line == '-- ':
                body += '-- \n'
                continue
            body += textwrap.fill(line, break_long_words=False) + '\n'
        for i, ref in enumerate(self.get_refs()):
            body += '\n' + '[%d] %s' % (i + 1, ref)
        return body.rstrip()

    def send(self):
        sendmail = aurweb.config.get('notifications', 'sendmail')
        sender = aurweb.config.get('notifications', 'sender')
        reply_to = aurweb.config.get('notifications', 'reply-to')
        reason = self.__class__.__name__
        if reason.endswith('Notification'):
            reason = reason[:-len('Notification')]

        for recipient in self.get_recipients():
            to, lang = recipient
            msg = email.mime.text.MIMEText(self.get_body_fmt(lang),
                                           'plain', 'utf-8')
            msg['Subject'] = self.get_subject(lang)
            msg['From'] = sender
            msg['Reply-to'] = reply_to
            msg['To'] = to
            if self.get_cc():
                msg['Cc'] = str.join(', ', self.get_cc())
            msg['X-MPR-Reason'] = reason
            msg['Date'] = email.utils.formatdate(localtime=True)

            for key, value in self.get_headers().items():
                msg[key] = value

            sendmail = aurweb.config.get('notifications', 'sendmail')
            if sendmail:
                # send email using the sendmail binary specified in the
                # configuration file
                p = subprocess.Popen([sendmail, '-t', '-oi'],
                                     stdin=subprocess.PIPE)
                p.communicate(msg.as_bytes())
            else:
                # send email using smtplib; no local MTA required
                server_addr = aurweb.config.get('notifications', 'smtp-server')
                server_port = aurweb.config.getint('notifications',
                                                   'smtp-port')
                use_ssl = aurweb.config.getboolean('notifications',
                                                   'smtp-use-ssl')
                use_starttls = aurweb.config.getboolean('notifications',
                                                        'smtp-use-starttls')
                user = aurweb.config.get('notifications', 'smtp-user')
                passwd = aurweb.config.get('notifications', 'smtp-password')

                if use_ssl:
                    server = smtplib.SMTP_SSL(server_addr, server_port)
                else:
                    server = smtplib.SMTP(server_addr, server_port)

                if use_starttls:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()

                if user and passwd:
                    server.login(user, passwd)

                server.set_debuglevel(0)
                deliver_to = [to] + self.get_cc()
                server.sendmail(sender, deliver_to, msg.as_bytes())
                server.quit()


class ResetKeyNotification(Notification):
    def __init__(self, conn, uid):
        cur = conn.execute('SELECT UserName, Email, BackupEmail, ' +
                           'LangPreference, ResetKey ' +
                           'FROM Users WHERE ID = ? AND Suspended = 0', [uid])
        self._username, self._to, self._backup, self._lang, self._resetkey = \
            cur.fetchone()
        super().__init__()

    def get_recipients(self):
        if self._backup:
            return [(self._to, self._lang), (self._backup, self._lang)]
        else:
            return [(self._to, self._lang)]

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate('MPR Password Reset', lang)

    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'A password reset request was submitted for the account '
            '{user} associated with your email address. If you wish to '
            'reset your password follow the link [1] below, otherwise '
            'ignore this message and nothing will happen.',
            lang).format(user=self._username)

    def get_refs(self):
        return (aur_location + '/passreset/?resetkey=' + self._resetkey,)


class WelcomeNotification(ResetKeyNotification):
    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'Welcome to the makedeb Package Repository',
            lang)

    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'Welcome to the makedeb Package Repository! In order to set an '
            'initial password for your new account, please click the '
            'link [1] below. If the link does not work, try copying and '
            'pasting it into your browser.', lang)


class CommentNotification(Notification):
    def __init__(self, conn, uid, pkgbase_id, comment_id):
        self._user = username_from_id(conn, uid)
        self._pkgbase = pkgbase_from_id(conn, pkgbase_id)
        cur = conn.execute('SELECT DISTINCT Users.Email, Users.LangPreference '
                           'FROM Users INNER JOIN PackageNotifications ' +
                           'ON PackageNotifications.UserID = Users.ID WHERE ' +
                           'Users.CommentNotify = 1 AND ' +
                           'PackageNotifications.UserID != ? AND ' +
                           'PackageNotifications.PackageBaseID = ? AND ' +
                           'Users.Suspended = 0',
                           [uid, pkgbase_id])
        self._recipients = cur.fetchall()
        cur = conn.execute('SELECT Comments FROM PackageComments WHERE ID = ?',
                           [comment_id])
        self._text = cur.fetchone()[0]
        super().__init__()

    def get_recipients(self):
        return self._recipients

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'MPR Comment for {pkgbase}',
            lang).format(pkgbase=self._pkgbase)

    def get_body(self, lang):
        body = aurweb.l10n.translator.translate(
            '{user} [1] added the following comment to {pkgbase} [2]:',
            lang).format(user=self._user, pkgbase=self._pkgbase)
        body += '\n\n' + self._text + '\n\n-- \n'
        dnlabel = aurweb.l10n.translator.translate(
            'Disable notifications', lang)
        body += aurweb.l10n.translator.translate(
            'If you no longer wish to receive notifications about this '
            'package, please go to the package page [2] and select '
            '"{label}".', lang).format(label=dnlabel)
        return body

    def get_refs(self):
        return (aur_location + '/account/' + self._user + '/',
                aur_location + '/pkgbase/' + self._pkgbase + '/')

    def get_headers(self):
        thread_id = '<pkg-notifications-' + self._pkgbase + \
                    '@aur.archlinux.org>'
        return headers_reply(thread_id)


class UpdateNotification(Notification):
    def __init__(self, conn, uid, pkgbase_id):
        self._user = username_from_id(conn, uid)
        self._pkgbase = pkgbase_from_id(conn, pkgbase_id)
        cur = conn.execute('SELECT DISTINCT Users.Email, ' +
                           'Users.LangPreference FROM Users ' +
                           'INNER JOIN PackageNotifications ' +
                           'ON PackageNotifications.UserID = Users.ID WHERE ' +
                           'Users.UpdateNotify = 1 AND ' +
                           'PackageNotifications.UserID != ? AND ' +
                           'PackageNotifications.PackageBaseID = ? AND ' +
                           'Users.Suspended = 0',
                           [uid, pkgbase_id])
        self._recipients = cur.fetchall()
        super().__init__()

    def get_recipients(self):
        return self._recipients

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'MPR Package Update: {pkgbase}',
            lang).format(pkgbase=self._pkgbase)

    def get_body(self, lang):
        body = aurweb.l10n.translator.translate(
            '{user} [1] pushed a new commit to {pkgbase} [2].',
            lang).format(user=self._user, pkgbase=self._pkgbase)
        body += '\n\n-- \n'
        dnlabel = aurweb.l10n.translator.translate(
            'Disable notifications', lang)
        body += aurweb.l10n.translator.translate(
            'If you no longer wish to receive notifications about this '
            'package, please go to the package page [2] and select '
            '"{label}".', lang).format(label=dnlabel)
        return body

    def get_refs(self):
        return (aur_location + '/account/' + self._user + '/',
                aur_location + '/pkgbase/' + self._pkgbase + '/')

    def get_headers(self):
        thread_id = '<pkg-notifications-' + self._pkgbase + \
                    '@aur.archlinux.org>'
        return headers_reply(thread_id)


class FlagNotification(Notification):
    def __init__(self, conn, uid, pkgbase_id):
        self._user = username_from_id(conn, uid)
        self._pkgbase = pkgbase_from_id(conn, pkgbase_id)
        cur = conn.execute(
            'SELECT DISTINCT Users.Email, ' +
            'Users.LangPreference FROM Users ' +
            'LEFT JOIN PackageComaintainers ' +
            'ON PackageComaintainers.UsersID = Users.ID ' +
            'INNER JOIN PackageBases ' +
            'ON PackageBases.MaintainerUID = Users.ID OR ' +
            'PackageBases.ID = PackageComaintainers.PackageBaseID ' +
            'WHERE PackageBases.ID = ? AND ' +
            'Users.Suspended = 0', [pkgbase_id])
        self._recipients = cur.fetchall()
        cur = conn.execute('SELECT FlaggerComment FROM PackageBases WHERE ' +
                           'ID = ?', [pkgbase_id])
        self._text = cur.fetchone()[0]
        super().__init__()

    def get_recipients(self):
        return self._recipients

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'MPR Out-of-date Notification for {pkgbase}',
            lang).format(pkgbase=self._pkgbase)

    def get_body(self, lang):
        body = aurweb.l10n.translator.translate(
            'Your package {pkgbase} [1] has been flagged out-of-date by '
            '{user} [2]:', lang).format(pkgbase=self._pkgbase,
                                        user=self._user)
        body += '\n\n' + self._text
        return body

    def get_refs(self):
        return (aur_location + '/pkgbase/' + self._pkgbase + '/',
                aur_location + '/account/' + self._user + '/')


class OwnershipEventNotification(Notification):
    def __init__(self, conn, uid, pkgbase_id):
        self._user = username_from_id(conn, uid)
        self._pkgbase = pkgbase_from_id(conn, pkgbase_id)
        cur = conn.execute('SELECT DISTINCT Users.Email, ' +
                           'Users.LangPreference FROM Users ' +
                           'INNER JOIN PackageNotifications ' +
                           'ON PackageNotifications.UserID = Users.ID WHERE ' +
                           'Users.OwnershipNotify = 1 AND ' +
                           'PackageNotifications.UserID != ? AND ' +
                           'PackageNotifications.PackageBaseID = ? AND ' +
                           'Users.Suspended = 0',
                           [uid, pkgbase_id])
        self._recipients = cur.fetchall()
        cur = conn.execute('SELECT FlaggerComment FROM PackageBases WHERE ' +
                           'ID = ?', [pkgbase_id])
        self._text = cur.fetchone()[0]
        super().__init__()

    def get_recipients(self):
        return self._recipients

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'MPR Ownership Notification for {pkgbase}',
            lang).format(pkgbase=self._pkgbase)

    def get_refs(self):
        return (aur_location + '/pkgbase/' + self._pkgbase + '/',
                aur_location + '/account/' + self._user + '/')


class AdoptNotification(OwnershipEventNotification):
    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'The package {pkgbase} [1] was adopted by {user} [2].',
            lang).format(pkgbase=self._pkgbase, user=self._user)


class DisownNotification(OwnershipEventNotification):
    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'The package {pkgbase} [1] was disowned by {user} '
            '[2].', lang).format(pkgbase=self._pkgbase,
                                 user=self._user)


class ComaintainershipEventNotification(Notification):
    def __init__(self, conn, uid, pkgbase_id):
        self._pkgbase = pkgbase_from_id(conn, pkgbase_id)
        cur = conn.execute('SELECT Email, LangPreference FROM Users ' +
                           'WHERE ID = ? AND Suspended = 0', [uid])
        self._to, self._lang = cur.fetchone()
        super().__init__()

    def get_recipients(self):
        return [(self._to, self._lang)]

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'MPR Co-Maintainer Notification for {pkgbase}',
            lang).format(pkgbase=self._pkgbase)

    def get_refs(self):
        return (aur_location + '/pkgbase/' + self._pkgbase + '/',)


class ComaintainerAddNotification(ComaintainershipEventNotification):
    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'You were added to the co-maintainer list of {pkgbase} [1].',
            lang).format(pkgbase=self._pkgbase)


class ComaintainerRemoveNotification(ComaintainershipEventNotification):
    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'You were removed from the co-maintainer list of {pkgbase} '
            '[1].', lang).format(pkgbase=self._pkgbase)


class DeleteNotification(Notification):
    def __init__(self, conn, uid, old_pkgbase_id, new_pkgbase_id=None):
        self._user = username_from_id(conn, uid)
        self._old_pkgbase = pkgbase_from_id(conn, old_pkgbase_id)
        if new_pkgbase_id:
            self._new_pkgbase = pkgbase_from_id(conn, new_pkgbase_id)
        else:
            self._new_pkgbase = None
        cur = conn.execute('SELECT DISTINCT Users.Email, ' +
                           'Users.LangPreference FROM Users ' +
                           'INNER JOIN PackageNotifications ' +
                           'ON PackageNotifications.UserID = Users.ID WHERE ' +
                           'PackageNotifications.UserID != ? AND ' +
                           'PackageNotifications.PackageBaseID = ? AND ' +
                           'Users.Suspended = 0',
                           [uid, old_pkgbase_id])
        self._recipients = cur.fetchall()
        super().__init__()

    def get_recipients(self):
        return self._recipients

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'MPR Package deleted: {pkgbase}',
            lang).format(pkgbase=self._old_pkgbase)

    def get_body(self, lang):
        if self._new_pkgbase:
            dnlabel = aurweb.l10n.translator.translate(
                'Disable notifications', lang)
            return aurweb.l10n.translator.translate(
                '{user} [1] merged {old} [2] into {new} [3].\n\n'
                '-- \n'
                'If you no longer wish receive notifications about the '
                'new package, please go to [3] and click "{label}".',
                lang).format(user=self._user, old=self._old_pkgbase,
                             new=self._new_pkgbase, label=dnlabel)
        else:
            return aurweb.l10n.translator.translate(
                '{user} [1] deleted {pkgbase} [2].\n\n'
                'You will no longer receive notifications about this '
                'package.', lang).format(user=self._user,
                                         pkgbase=self._old_pkgbase)

    def get_refs(self):
        refs = (aur_location + '/account/' + self._user + '/',
                aur_location + '/pkgbase/' + self._old_pkgbase + '/')
        if self._new_pkgbase:
            refs += (aur_location + '/pkgbase/' + self._new_pkgbase + '/',)
        return refs


class RequestOpenNotification(Notification):
    def __init__(self, conn, uid, reqid, reqtype, pkgbase_id, merge_into=None):
        self._user = username_from_id(conn, uid)
        self._pkgbase = pkgbase_from_id(conn, pkgbase_id)
        cur = conn.execute(
            'SELECT DISTINCT Users.Email FROM PackageRequests ' +
            'INNER JOIN PackageBases ' +
            'ON PackageBases.ID = PackageRequests.PackageBaseID ' +
            'LEFT JOIN PackageComaintainers ' +
            'ON PackageComaintainers.PackageBaseID = PackageRequests.PackageBaseID ' +
            'INNER JOIN Users ' +
            'ON Users.ID = PackageRequests.UsersID ' +
            'OR Users.ID = PackageBases.MaintainerUID ' +
            'OR Users.ID = PackageComaintainers.UsersID ' +
            'WHERE PackageRequests.ID = ? AND ' +
            'Users.Suspended = 0', [reqid])
        self._to = aurweb.config.get('options', 'aur_request_ml')
        self._cc = [row[0] for row in cur.fetchall()]
        cur = conn.execute('SELECT Comments FROM PackageRequests WHERE ID = ?',
                           [reqid])
        self._text = cur.fetchone()[0]
        self._reqid = int(reqid)
        self._reqtype = reqtype
        self._merge_into = merge_into

    def get_recipients(self):
        return [(self._to, 'en')]

    def get_cc(self):
        return self._cc

    def get_subject(self, lang):
        return '[PRQ#%d] %s Request for %s' % \
               (self._reqid, self._reqtype.title(), self._pkgbase)

    def get_body(self, lang):
        if self._merge_into:
            body = '%s [1] filed a request to merge %s [2] into %s [3]:' % \
                   (self._user, self._pkgbase, self._merge_into)
            body += '\n\n' + self._text
        else:
            an = 'an' if self._reqtype[0] in 'aeiou' else 'a'
            body = '%s [1] filed %s %s request for %s [2]:' % \
                   (self._user, an, self._reqtype, self._pkgbase)
            body += '\n\n' + self._text
        return body

    def get_refs(self):
        refs = (aur_location + '/account/' + self._user + '/',
                aur_location + '/pkgbase/' + self._pkgbase + '/')
        if self._merge_into:
            refs += (aur_location + '/pkgbase/' + self._merge_into + '/',)
        return refs

    def get_headers(self):
        thread_id = '<pkg-request-' + str(self._reqid) + '@aur.archlinux.org>'
        # Use a deterministic Message-ID for the first email referencing a
        # request.
        headers = headers_msgid(thread_id)
        return headers


class RequestCloseNotification(Notification):
    def __init__(self, conn, uid, reqid, reason):
        self._user = username_from_id(conn, uid) if int(uid) else None

        cur = conn.execute(
            'SELECT DISTINCT Users.Email FROM PackageRequests ' +
            'INNER JOIN PackageBases ' +
            'ON PackageBases.ID = PackageRequests.PackageBaseID ' +
            'LEFT JOIN PackageComaintainers ' +
            'ON PackageComaintainers.PackageBaseID = PackageRequests.PackageBaseID ' +
            'INNER JOIN Users ' +
            'ON Users.ID = PackageRequests.UsersID ' +
            'OR Users.ID = PackageBases.MaintainerUID ' +
            'OR Users.ID = PackageComaintainers.UsersID ' +
            'WHERE PackageRequests.ID = ? AND ' +
            'Users.Suspended = 0', [reqid])
        self._to = aurweb.config.get('options', 'aur_request_ml')
        self._cc = [row[0] for row in cur.fetchall()]
        cur = conn.execute('SELECT PackageRequests.ClosureComment, ' +
                           'RequestTypes.Name, ' +
                           'PackageRequests.PackageBaseName ' +
                           'FROM PackageRequests ' +
                           'INNER JOIN RequestTypes ' +
                           'ON RequestTypes.ID = PackageRequests.ReqTypeID ' +
                           'WHERE PackageRequests.ID = ?', [reqid])
        self._text, self._reqtype, self._pkgbase = cur.fetchone()
        self._reqid = int(reqid)
        self._reason = reason

    def get_recipients(self):
        return [(self._to, 'en')]

    def get_cc(self):
        return self._cc

    def get_subject(self, lang):
        return '[PRQ#%d] %s Request for %s %s' % (self._reqid,
                                                  self._reqtype.title(),
                                                  self._pkgbase,
                                                  self._reason.title())

    def get_body(self, lang):
        if self._user:
            body = 'Request #%d has been %s by %s [1]' % \
                   (self._reqid, self._reason, self._user)
        else:
            body = 'Request #%d has been %s automatically by the makedeb Package ' \
                   'Repository package request system' % \
                   (self._reqid, self._reason)
        if self._text.strip() == '':
            body += '.'
        else:
            body += ':\n\n' + self._text
        return body

    def get_refs(self):
        if self._user:
            return (aur_location + '/account/' + self._user + '/',)
        else:
            return ()

    def get_headers(self):
        thread_id = '<pkg-request-' + str(self._reqid) + '@aur.archlinux.org>'
        headers = headers_reply(thread_id)
        return headers


class TUVoteReminderNotification(Notification):
    def __init__(self, conn, vote_id):
        self._vote_id = int(vote_id)
        cur = conn.execute('SELECT Email, LangPreference FROM Users ' +
                           'WHERE AccountTypeID IN (2, 4) AND ID NOT IN ' +
                           '(SELECT UserID FROM TU_Votes ' +
                           'WHERE TU_Votes.VoteID = ?) AND ' +
                           'Users.Suspended = 0', [vote_id])
        self._recipients = cur.fetchall()
        super().__init__()

    def get_recipients(self):
        return self._recipients

    def get_subject(self, lang):
        return aurweb.l10n.translator.translate(
            'TU Vote Reminder: Proposal {id}',
            lang).format(id=self._vote_id)

    def get_body(self, lang):
        return aurweb.l10n.translator.translate(
            'Please remember to cast your vote on proposal {id} [1]. '
            'The voting period ends in less than 48 hours.',
            lang).format(id=self._vote_id)

    def get_refs(self):
        return (aur_location + '/tu/?id=' + str(self._vote_id),)


def main():
    action = sys.argv[1]
    action_map = {
        'send-resetkey': ResetKeyNotification,
        'welcome': WelcomeNotification,
        'comment': CommentNotification,
        'update': UpdateNotification,
        'flag': FlagNotification,
        'adopt': AdoptNotification,
        'disown': DisownNotification,
        'comaintainer-add': ComaintainerAddNotification,
        'comaintainer-remove': ComaintainerRemoveNotification,
        'delete': DeleteNotification,
        'request-open': RequestOpenNotification,
        'request-close': RequestCloseNotification,
        'tu-vote-reminder': TUVoteReminderNotification,
    }

    conn = aurweb.db.Connection()

    notification = action_map[action](conn, *sys.argv[2:])
    notification.send()

    conn.commit()
    conn.close()


if __name__ == '__main__':
    main()
