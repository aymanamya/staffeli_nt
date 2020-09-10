import os
import sys
import tempfile

from pathlib import Path

from vas import *
from util import *

NAME_SHEET = 'grade.yml'

def grade(submission, grade, feedback, dry_run=True):
    # bail if dry
    print('Submit: user_id=%d, grade=%s' % (submission.user_id, grade))
    if dry_run:
        return

    # set grade and load comments
    if submission.score is None or abs(submission.score - grade) > 0.001:
        submission.edit(submission={'posted_grade': grade})
    else:
        submission.edit()

    # check if feedback is already uploaded
    duplicate = False
    for comment in submission.submission_comments:
        try:
            attachments = comment['attachments']
        except KeyError:
            attachments = []

        print('Comment with:', len(attachments), 'attachments')
        for attachment in attachments:
            if duplicate:
                break

            try:
                contents = download(attachment['url']).decode('utf-8')
            except UnicodeDecodeError:
                contents = ''

            duplicate = duplicate or contents.strip() == feedback.strip()

    # upload feedback if new
    if duplicate:
        print('Feedback already uploaded:', submission.user_id)

    else:
        print('Uploading new feedback:', submission.user_id)
        with tempfile.TemporaryDirectory() as c_dir:
            f_path = os.path.join(c_dir, 'feedback.txt')
            with open(f_path, 'w') as f:
                f.write(feedback)
            submission.upload_comment(f_path)

if __name__ == '__main__':

    path_template = sys.argv[1]
    path_submissions = sys.argv[2]
    live = '--live' in sys.argv
    step = '--step' in sys.argv

    sheets = []

    path_token = os.path.join(
        str(Path.home()),
        '.canvas.token'
    )

    meta = os.path.join(
        path_submissions,
        'meta.yml'
    )

    with open(meta, 'r') as f:
        meta = parse_meta(f.read())

    with open(path_template, 'r') as f:
        tmpl = parse_template(f.read())

    with open(path_token, 'r') as f:
        API_KEY = f.read().strip()

    # fetch every grading sheet
    for root, dirs, files in os.walk(path_submissions):
        for name in files:
            if name != NAME_SHEET:
                continue

            path = os.path.join(root, name)
            # print(path)
            with open(path, 'r') as f:
                sheets.append((
                    path,
                    parse_sheet(f.read())
                    ))

    # check that every sheet is complete
    graded = True
    for (path, sheet) in sheets:
        if not sheet.is_graded(tmpl):
            print('Sheet not graded:', path)
            graded = False

    if graded is False:
        print('Grading is not complete')


    # construct reverse map[user] -> grading sheet
    handins = {}
    for (_, sheet) in sheets:
        for student in sheet.students:
            assert student.id not in handins, 'student assigned multiple sheets'
            handins[student.id] = sheet

    # obtain canvas session
    API_URL = 'https://absalon.ku.dk/'

    canvas = Canvas(API_URL, API_KEY)
    course = canvas.get_course(meta.course.id)
    assignment = course.get_assignment(meta.assignment.id)

    if live:
        print('Uploading feedback to:', assignment)
        choice = input('Sure? (y/n) : ')
        assert choice.strip() == 'y'
    else:
        print('Doing a dry-run...')

    for submission in assignment.get_submissions():
        # get sheet
        try:
            uid = submission.user_id
            sheet = handins[uid]
        except KeyError:
            print('No handin for:', uid)
            continue

        # total score
        total = sheet.get_grade(tmpl)
        if total is None:
            continue

        # sanity check
        _ = handins[uid]

        if step:
            print(tmpl.format_md(sheet))
            print('-----------------------------------\n')
            input()
            print('\n'*3)

        grade(
            submission,
            total,
            tmpl.format_md(sheet),
            dry_run = not live
        )