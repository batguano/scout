# -*- coding: utf-8 -*-
###############################################################################
#
# Copyright (c) 2009, Gabriel Filion
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice,
#     * this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
###############################################################################
"""Utility classes for communicating with Tomboy over dbus.

Exceptions:
    ConnectionError -- A dbus connection problem occured.
    NoteNotFound    -- A note searched by name was not found.

Classes:
    Tomtom             -- Takes user input and calls the appropriate methods.
    TomboyCommunicator -- Communicates with dbus to fetch information on notes.
    TomboyNote         -- Object representation of a Tomboy note.

"""
import dbus
import datetime
import time
import sys
import os

# This must be modified with all version bumps!
tomtom_version = "0.2"

class ConnectionError(Exception):
    """Simple exception raised when contacting Tomboy via dbus fails."""
    pass

class NoteNotFound(Exception):
    """Simple exception raised when a specific note does not exist."""
    pass

class Tomtom(object):
    """Application class for Tomtom.

    Returns listings, note content or search results. Tomtom is the application
    entry point. It receives user input and calls the approriate methods to do
    the requested work.

    """
    def __init__(self):
        """Constructor.

        This method makes sure the communicator is instantiated.

        """
        super(Tomtom, self).__init__()
        self.tomboy_communicator = TomboyCommunicator()

    def get_notes(self, *args, **kwargs):
        """Get a list of notes"""
        # XXX temporary mapping method
        return self.tomboy_communicator.get_notes(*args, **kwargs)

    def get_note_content(self, note):
        """Get the contents of one note."""
        # XXX temporary mapping method
        return self.tomboy_communicator.get_note_content(note)

class TomboyCommunicator(object):
    """Interface between the application and Tomboy's dbus link."""
    def __init__(self):
        """Create a link to the Tomboy application upon instanciation."""
        try:
            tb_bus = dbus.SessionBus()
            tb_object = tb_bus.get_object(
                "org.gnome.Tomboy",
                "/org/gnome/Tomboy/RemoteControl"
            )
            self.comm = dbus.Interface(
                tb_object,
                "org.gnome.Tomboy.RemoteControl"
            )
        except dbus.DBusException, e:
            raise ConnectionError(
                """Could not establish connection with Tomboy. """ + \
                """Is it running?: %s""" % (e, )
            )

    def get_uris_for_n_notes(self, count_max):
        """Find the URIs for the `count_max` latest notes.

        This method retrieves URIs of notes. If count_max is None, it gets URIs
        for all notes. Otherwise, it gets `count_max` number of URIs.

        Arguments:
            count_max -- Maximum number of notes to lookup

        """
        uris = self.comm.ListAllNotes()

        if count_max != None:
            uris = uris[:count_max]

        return [(u, None) for u in uris]

    def get_uris_by_name(self, names):
        """Search for all the notes with the given names.

        This method retreives URIs of notes by searching for them by names. It
        searches for all names that are in the `names` list.

        Arguments:
            names -- a list of note names

        """
        uris = []

        for name in names:
            uri = self.comm.FindNote(name)
            if uri == dbus.String(""):
                raise NoteNotFound(name)

            uris.append( (uri, name) )

        return uris

    def filter_by_tags(self, notes, tag_list):
        """Remove notes from the list if they have no tags from the list."""
        tags = set(tag_list)

        return [
            note for note in notes
            if tags.intersection( set(note.tags) )
        ]

    def filter_out_templates(self, notes):
        """Take out those annoying templates from display."""
        return [n for n in notes if "system:template" not in n.tags]

    def build_note_list(self, **kwargs):
        """Find notes and build a list of TomboyNote objects.

        This method gets a list of notes from Tomboy and converts them to
        TomboyNote objects. It then returns the notes in a list.

        """
        names = kwargs.pop("names", [])
        count_limit = kwargs.pop("count_limit", None)

        if names:
            pairs = self.get_uris_by_name(names)
        else:
            pairs = self.get_uris_for_n_notes(count_limit)

        list_of_notes = []
        for pair in pairs:
            uri = pair[0]
            note_title = pair[1]

            if note_title is None:
                note_title = self.comm.GetNoteTitle(uri)

            list_of_notes.append(
                TomboyNote(
                    uri=uri,
                    title=note_title,
                    date=self.comm.GetNoteChangeDate(uri),
                    tags=self.comm.GetTagsForNote(uri)
                )
            )

        return list_of_notes

    def filter_notes(self, notes, tags=[], names=[],
            exclude_templates=True):
        """Filter a list of notes according to some criteria.

        Filter a list of TomboyNote objects according to a list of filtering
        options. "count_limit" can limit the number of notes returned. By
        default, it gets all notes. "names" will filter out any notes but those
        whose names are in the list.

        Arguments:
            notes -- list of note objects
            tags -- list of tag strings to filter by
            names -- list of the only names to include
            exclude_templates -- Boolean, exclude templates (default: True)

        """
        if tags:
            notes = self.filter_by_tags(notes, tags)

        # Force templates to be included in listing if the tag is requested.
        if "system:template" in tags:
            exclude_templates = False

        # Avoid filtering if names are specified. This makes it possible to
        # select a template by name. Also avoid if template tag is specified.
        if not names and exclude_templates:
            return self.filter_out_templates(notes)

        return notes

    def get_notes(self, **kwargs):
        """Get a list of notes from Tomboy.

        This function is the single point of entry to get a list of notes that
        will match the given selection options. The first step is to build a
        list of TomboyNote objects and the last step is to filter out this list
        according to the other options.

        Arguments:
            **kwargs -- Map of arguments used for getting and filtering notes.

        """
        # Consumes "names" and "count_limit" arguments
        notes = self.build_note_list(**kwargs)
        kwargs.pop("names", [])
        kwargs.pop("count_limit", 0)

        return self.filter_notes(notes, **kwargs)

    def get_note_content(self, note):
        """Get the content of a note.

        This method returns the content of one note. The note must be a
        TomboyNote object. Tags are added after the note name in the returned
        content.

        Arguments:
            note -- A TomboyNote object

        """
        lines = self.comm.GetNoteContents(note.uri).splitlines()
        #TODO Oddly (but it is good), splitting the lines makes the indentation
        # bullets appear.. come up with a test for this to stay
        if note.tags:
            lines[0] = "%s  (%s)" % ( lines[0], ", ".join(note.tags) )

        return os.linesep.join(lines)

class TomboyNote(object):
    """Object corresponding to a Tomboy note coming from dbus."""
    def __init__(self, uri, title="", date=dbus.Int64(), tags=[]):
        """Constructor.

        This makes sure that instance attributes are set upon the note's
        instantiation. The date can either be a dbus.Int64 object or a datetime
        object.

        Arguments:
            uri -- A string representing the note's URI
            title -- A string representing the note's title
            date -- Can either be a dbus.Int64 or datetime object
            tags -- A list of strings that represent tags

        """
        super(TomboyNote, self).__init__()
        self.uri = uri
        self.title = title
        self.tags = tags

        if isinstance(date, datetime.datetime):
            self.date = dbus.Int64( time.mktime(date.timetuple()) )
        else:
            self.date = date

    def listing(self):
        """Get a listing for this note.

        This method returns listing information about the note represented by
        this object.

        """
        printable_title = self.title
        if not self.title:
            printable_title = "_note doesn't have a name_"

        printable_tags = ""
        if len(self.tags):
            printable_tags = "  (" + ", ".join(self.tags) + ")"

        return "%(date)s | %(title)s%(tags)s" % \
            {
                "date": datetime.datetime.fromtimestamp(self.date)\
                            .isoformat()[:10],
                "title": printable_title,
                "tags": printable_tags,
            }

