#!/usr/bin/env python
# -*- coding: utf8 -*-

# Class to parse a MusicXML score into a pianoroll
# Input :
#       - division : the desired quantization in the pianoroll
#       - instru_dict : a dictionary
#       - total_length : the total length in number of quarter note of the parsed file
#            (this information can be accessed by first parsing the file with the durationParser)
#       - discard_grace : True to discard grace notes and not write them in the pianoroll
#
# A few remarks :
#       - Pianoroll : the different instrument are mapped from the name written in part-name
#           to a unique name. This mapping is done through regex indexed in instru_dict.
#           This dictionary is imported through the json format.
#

import numpy as np
import sys
import os
import xml.sax
import re
# Debug
import pdb
import matplotlib.pylab as plt
# from mpldatacursor import datacursor

mapping_step_midi = {
    'C': 0,
    'D': 2,
    'E': 4,
    'F': 5,
    'G': 7,
    'A': 9,
    'B': 11
}

mapping_dyn_number = {
    # Value drawn from http://www.wikiwand.com/en/Dynamics_%28music%29
    'ppp': 0.125,
    'pp': 0.258,
    'p': 0.383,
    'mp': 0.5,
    'mf': 0.625,
    'f': 0.75,
    'ff': 0.875,
    'fff': 0.984
}


class ScoreToPianorollHandler(xml.sax.ContentHandler):
    def __init__(self, division, instru_dict, total_length, discard_grace):
        self.CurrentElement = u""
        # Instrument
        self.instru_dict = instru_dict
        self.identifier = u""                # Current identifier
        self.part_instru_mapping = {}       # Mapping between parts in the parsed score,
        # and instrument name in the produced pianoroll
        self.content = u""

        # Measure informations
        self.time = 0              # time counter
        self.division_score = -1     # rhythmic quantization of the original score (in division of the quarter note)
        self.division_pianoroll = division  # thythmic quantization of the pianoroll we are writting

        # Current note information
        # Pitch
        self.pitch_set = False
        self.step = u""
        self.step_set = False
        self.octave = 0
        self.octave_set = False
        self.alter = 0
        # Is it a rest ?
        self.rest = False
        # Is it a chord ? (usefull for the staccati)
        self.chord = False
        # Time
        self.duration = 0
        self.duration_set = False
        # Voices are used for the articulation
        self.current_voice = u""
        self.voice_set = False
        # Deal with grace notes
        self.grace = False
        self.discard_grace = discard_grace

        # Pianoroll
        self.pianoroll = {}
        self.total_length = total_length

        # Stop flags
        self.articulation = {}
        # Tied notes (not phrasing)
        self.tie_type = None
        self.tying = {}  # Contains voice -> tie_on?
        # Staccati . Note that for chords the staccato tag is
        # ALWAYS on the first note of the chord if the file is correctly written
        self.previous_staccato = False
        self.staccato = False

        # Time evolution of the dynamics
        self.writting_dynamic = False
        self.fp = False
        self.dynamics = {}
        # Directions
        self.direction_type = None
        self.direction_start = None
        self.direction_stop = None

        ####################################################################
        ####################################################################
        ####################################################################
    def startElement(self, tag, attributes):
        self.CurrentElement = tag

        # Part information
        if tag == u"score-part":
            self.identifier = attributes[u'id']
        if tag == u"part":
            self.identifier = attributes[u'id']
            # And set to zeros time information
            self.time = 0
            self.division_score = -1
            # Initialize the pianoroll
            instrument = self.part_instru_mapping[self.identifier]
            self.pianoroll[instrument] = np.zeros([self.total_length * self.division_pianoroll, 128], dtype=np.int)
            # Initialize the articulations
            self.tie_type = None
            self.tying = {}  # Contains voice -> tie_on?
            self.articulation[instrument] = np.zeros([self.total_length * self.division_pianoroll, 128], dtype=np.int)
            # Initialize the dynamics
            self.dynamics[instrument] = np.zeros([self.total_length * self.division_pianoroll], dtype=np.float)

        if tag == u'rest':
            self.rest = True
        if tag == u'chord':
            if self.duration_set:
                raise NameError('A chord tag should be placed before the duration tag of the current note')
            self.time -= self.duration
            self.chord = True
        if tag == u'grace':
            self.grace = True

        ####################################################################
        if tag == u'tie':
            self.tie_type = attributes[u'type']

        if tag == u'staccato':
            # pdb.set_trace()
            self.staccato = True

        ####################################################################
        # Dynamics
        if tag in mapping_dyn_number:
            instru = self.part_instru_mapping[self.identifier]
            self.dynamics[instru][self.time:] = mapping_dyn_number[tag]
        elif tag in (u"sf", u"sfz", u"sffz", u"fz"):
            instru = self.part_instru_mapping[self.identifier]
            self.dynamics[instru][self.time] = mapping_dyn_number[u'fff']
        elif tag == u'fp':
            instru = self.part_instru_mapping[self.identifier]
            self.dynamics[instru][self.time:] = mapping_dyn_number[u'f']
            self.fp = True

        # Directions
        # Cresc end dim are written with an arbitrary slope, then adjusted after the file
        # has been parsed by a smoothing function
        if tag == u'wedge':
            instru = self.part_instru_mapping[self.identifier]
            if attributes[u'type'] in (u'diminuendo', u'crescendo'):
                self.direction_start = int(self.time * self.division_pianoroll / self.division_score)
                self.direction_type = attributes[u'type']
            elif attributes[u'type'] == u'stop':
                self.direction_stop = int(self.time * self.division_pianoroll / self.division_score)
                if self.direction_start is None:
                    raise NameError('Stop flag for a direction, but no direction has been started')
                starting_dyn = self.dynamics[instru][self.direction_start]
                if self.direction_type == u'crescendo':
                    ending_dyn = min(starting_dyn + 0.1, 1)
                    self.dynamics[instru][self.direction_start:self.direction_stop] = \
                        np.linspace(starting_dyn, ending_dyn, self.direction_stop - self.direction_start)
                elif self.direction_type == u'diminuendo':
                    ending_dyn = max(starting_dyn - 0.1, 0)
                    self.dynamics[instru][self.direction_start:self.direction_stop] = \
                        np.linspace(starting_dyn, ending_dyn, self.direction_stop - self.direction_start)
                # Fill the end of the score with the ending value
                self.dynamics[instru][self.direction_stop:] = ending_dyn
                self.direction_start = None
                self.direction_stop = None

        ###################################################################
        ###################################################################
        ###################################################################
    def endElement(self, tag):
        if tag == u'pitch':
            if self.octave_set and self.step_set:
                self.pitch_set = True
            self.octave_set = False
            self.step_set = False

        if tag == u"note":
            # When leaving a note tag, write it in the pianoroll
            if not self.duration_set:
                if not self.grace:
                    raise NameError("XML misformed, a Duration tag is missing")

            not_a_rest = not self.rest
            not_a_grace = not self.grace or not self.discard_grace
            if not_a_rest and not_a_grace:
                # Check file integrity
                if not self.pitch_set:
                    print "XML misformed, a Pitch tag is missing"
                    return
                # Get instru
                instru = self.part_instru_mapping[self.identifier]
                # Start and end time for the note
                start_time = int(self.time * self.division_pianoroll / self.division_score)
                if self.grace:
                    end_time = start_time
                    # A grace note is an anticipation
                    start_time -= 1
                else:
                    end_time = int((self.time + self.duration) * self.division_pianoroll / self.division_score)
                # Its pitch
                midi_pitch = mapping_step_midi[self.step] + self.octave * 12 + self.alter
                # Write it in the pianoroll
                self.pianoroll[instru][start_time:end_time, midi_pitch] = int(1)

                ####################################################################
                ############################
                ############################
                # # # # D  E  B  U   G
                # print self.step
                # print start_time
                # print end_time
                # if instru == 'Piano':
                #     pdb.set_trace()
                ############################
                ############################

                voice = u'1'
                if self.voice_set:
                    voice = self.current_voice

                # Initialize if the voice has not been seen before
                if voice not in self.tying:
                    self.tying[voice] = False

                # Note that tying[voice] can't be set when opening the tie tag since
                # the current voice is not knew at this time
                if self.tie_type == u"start":
                    # Allows to keep on the tying if it spans over several notes
                    self.tying[voice] = True
                if self.tie_type == u"stop":
                    self.tying[voice] = False

                tie = self.tying[voice]

                # Staccati
                if self.chord:
                    self.staccato = self.previous_staccato
                staccato = self.staccato

                if (not tie) and (not staccato):
                    self.articulation[instru][start_time:end_time - 1, midi_pitch] = int(1)
                if tie:
                    self.articulation[instru][start_time:end_time, midi_pitch] = int(1)
                if staccato:
                    self.articulation[instru][start_time:start_time + 1, midi_pitch] = int(1)
                ####################################################################
                # Forte-piano
                if self.fp:
                    self.dynamics[start_time:] = mapping_dyn_number[u'p']
                    self.fp = False
                ####################################################################

            # Increment the time counter
            if not self.grace:
                self.time += self.duration
            # Set to "0" different values
            self.pitch_set = False
            self.duration_set = False
            self.alter = 0
            self.rest = False
            self.grace = False
            self.voice_set = False
            self.tie_type = None
            self.previous_staccato = self.staccato
            self.staccato = False
            self.chord = False

        if tag == u'backup':
            if not self.duration_set:
                raise NameError("XML Duration not set for a backup")
            self.time -= self.duration
            self.duration_set = False

        if tag == u'forward':
            if not self.duration_set:
                raise NameError("XML Duration not set for a forward")
            self.time += self.duration
            self.duration_set = False

        if tag == u'part-name':
            part_name = self.content
            is_found_instru = False
            # find the name in our dictionnary
            for instru_name, set_name in self.instru_dict.iteritems():
                # Match by regular expression
                if search_re_list(part_name, set_name):
                    # Check if part name match any of the value in set_name
                    this_instru_name = instru_name
                    is_found_instru = True
                    break

            if not is_found_instru:
                print '\n______________________________________'
                print (u'Enter an instrument name for the part name ' + part_name).encode('utf8')
                print '(Be careful to use the same name as those shown before if this instrument already exists)\n'
                print '\n'.join(self.instru_dict.keys())
                print '______________________________________'
                # Get the name of the instrument
                this_instru_name = raw_input().decode(sys.stdin.encoding)

                print 'Enter an associated regular expression :'
                print '______________________________________\n'
                re_instru = raw_input().decode(sys.stdin.encoding)
                # Add the name of the part to the list corresponding to this instrument in the dictionary
                if this_instru_name in self.instru_dict.keys():
                    self.instru_dict[this_instru_name].append(re_instru)
                else:
                    self.instru_dict[this_instru_name] = [re_instru]

            print (u"@@ " + self.content + u"   :   " + this_instru_name).encode('utf8')
            self.content = u""
            self.part_instru_mapping[self.identifier] = this_instru_name
        ####################################################################

        ####################################################################
        ####################################################################
        ####################################################################
    def characters(self, content):
        # Avoid breaklines and whitespaces
        if content.strip():
            # Time and measure informations
            if self.CurrentElement == u"divisions":
                self.division_score = int(content)

            # Note informations
            if self.CurrentElement == u"duration":
                self.duration = int(content)
                self.duration_set = True
            if self.CurrentElement == u"step":
                self.step = content
                self.step_set = True
            if self.CurrentElement == u"octave":
                self.octave = int(content)
                self.octave_set = True
            if self.CurrentElement == u"alter":
                self.alter = int(content)
            if self.CurrentElement == u"voice":
                self.current_voice = content
                self.voice_set = True

            if self.CurrentElement == u"part-name":
                self.content += u" " + content

            ############################################################
            # Directions
            if self.CurrentElement == u'words':
                # We consider that a written dim or cresc approximately span over 4 quarter notes.
                # If its less its gonna be overwritten by the next dynamic
                is_cresc = re.match(u'$[cC]res.*', content)
                is_dim = re.match(u'$[dD]im.*', content)
                if is_dim or is_cresc:
                    instru = self.part_instru_mapping[self.identifier]
                    t_start = int(self.time * self.division_pianoroll / self.division_score)
                    t_end = t_start + 4 * self.division_pianoroll
                    start_dyn = self.dynamics[instru][t_start]
                    if is_cresc:
                        self.dynamics[instru][t_start:t_end] = np.linspace(start_dyn, max(start_dyn + 0.1, 1), t_end - t_start)
                    if is_dim:
                        self.dynamics[instru][t_start:t_end] = np.linspace(start_dyn, min(start_dyn - 0.1, 0), t_end - t_start)


def search_re_list(string, expression):
    for value in expression:
        result_re = re.search(value, string, flags=re.IGNORECASE | re.UNICODE)
        if result_re is not None:
            return True
    return False


if __name__ == "__main__":
    instru_dict = {
        'Voice': ['Voice'],
        'Piano': ['Piano']
    }
    # create an XMLReader
    parser = xml.sax.make_parser()
    # turn off namepsaces
    parser.setFeature(xml.sax.handler.feature_namespaces, 0)

    # override the default ContextHandler
    Handler_score = ScoreToPianorollHandler(4, instru_dict, 120)
    parser.setContentHandler(Handler_score)

    print "cest parti\n"
    if(os.path.isfile("BeetAnGeSample.xml")):
        parser.parse("BeetAnGeSample.xml")
    else:
        print "Not a file"

    data = Handler_score.pianoroll['Piano']
    np.savetxt("foo.csv", data, delimiter=";", fmt='%1i')
    plt.imshow(data, interpolation='nearest', cmap='bone', origin='lower')
    plt.show()