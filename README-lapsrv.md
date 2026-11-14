> Historical design notes. For current MCP connections and saved GUI settings, see [README.md](README.md). Workbook/WebSocket startup instructions below are superseded.

# lapsrv

Lapsrv is a python app that uses an Impinj RFID reader placed about 50m before the finish line to 
get early tag reads from the racers and display that information in realtime in the application window
and alternately via a web interface.  

Lapsrv will emulate the CrossMgr's RFID protocol to collect the tag reads from the Impinj4 program. The Impinj4
program will be configured to support an additional RFID reader that will send data to a different (non CrossMgr)
laptop running lapsrv. These tag reads will only got to lapsrv and not to CrossMgr.

Lapsrv will connect to CrossMgr via the CrossMgr's WebSocket API's to get the current race information, e.g.
the current laps for each category.

Lapsrv will use the CrossMgr's race XLSX configuration file to get the race information, e.g. category names, laps, and
the racer information, names, category bib numbers, teams etc.

Lapsrv will display the information in a tkinter application window, and also make the information available via a 
web interface that can be accessed from a mobile phone or tablet. 

Typically this replaces having a person standing 50m before the finish line with a radio to provide similiar
information to the officials at the finish line. By having this information available this eliminates the need
for a person and provides more complete and accurate information.

The distance is only limited to availability of power and a network (WiFi or Ethernet) connection back to the 
finish line.

## Overview Of Display

The intent is to show actionable information to the race officials at the finish line. While the same information 
will be available from CrossMgr after the racers cross the line at the finish line, by the time it is display the 
peloton will be well past the finish line. By using early reads from 50m up the road the officials can make 
decisions based on what category is about to cross the line. This can be used for example to ensure that the
bell gets rung for the last lap of a category.

### Categories

The top area of the display will show the categories that have been seen in the last 10 seconds with a count
of the number of racers in each category, the number of laps to go for the category, and if they are seeing
one lap to go, the bell icon will be shown. The categories will be sorted by the number of racers in each category.

This information will display in a reasonably large font.

Data fields:
```| Category | Count | Laps To Go | Bell |
```

### Racers

The bottom of the screen will show the racers that have been seen, sorted by arrival time, oldest at the top, most recent 
at the bottom, with the information scrolling up as new data is received. And being able to be scrolled up and down by 
the user to review.

Data fields:
```
| Bib | Note | Time | Gap | Lap | Name | Category | Team | ETA |
```

- Bib
- Note - position in category, Lead, 1st, 
- Time - race time of the read
- Gap - time gap to the previous racer in the same group, or -N laps if rider has been lapped by leader
- Lap - current laps completed, 
- Name - name of the racer
- Category - category of the racer
- Team - team of the racer
- ETA - estimated time to finish based on current speed and distance to finish line 

N.b. ETA only on the per category page.

## CrossMgr WebSocket API

There are two WebSocket API's that lapsrv will use to get information from CrossMgr. See these
html files for details of the java script to connect to the WebSocket API's and display the information 
as a web page. These can be used as a starting point for accessing the WebSocket API's from lapsrv.

- Announcer.html - Live Results
- LapCounter.html - Current Laps for each category

## Announcer
```
Passings | [Cat Name] | [ Cat Name] | [ Cat Name] | ...
Category | Pos | Gag | Name | Team | Bib
```

### Passings
Passing data for all categories

## Cat Name
Shows summary of category: "Junior (Men): 4 laps to go, 31.65 km/h
Passing data for the category.


## CrossMgr XLSX Configuration File

Three tabs:
- Registration
- --CrossMgr-Categories
- --CrossMgr-Properties

### Registration
```
Bib#	LastName	FirstName	Team	City	StateProv	Category	Age	Gender	License	NatCode	UCI ID	Tag
2	Allan	Aubrey	Independent		Manitoba	Cat 1/2	18	Men	MB72015		101 268 926 53	1FA1F96E79C1F1F1C534814D
746	Anderson	Quinn	Lost Boys Book Club	Richmond	BC	Master	51	Men	PR2315305	CAN	100 548 255 92	CA5D4278DDD9014000000000
362	Aparicio	Oscar	Black Bear Racing		British Columbia	Cat 3	33	Men	BC009129	ESA		266666818EF2ABFEFB9068AB
100	Ayroud	Kathryn	Red Truck Racing p/b Mosaic Homes	Edmonton	AB	Cat 1/2/3	24	Women	AB60299		100 822 400 18	D72F0101FE6A1ADB9269A985

```
### --CrossMgr-Categories
```
Category Type	Name	Gender	Numbers	Start Offset	Race Laps	Race Distance	Race Minutes	Publish	Upload	Series
Wave	Cat 1/2	Open	2-65	0:00	16	6.1		TRUE	TRUE	TRUE
Wave	Cat 3	Open	300-365	3:00	15	6.1		TRUE	TRUE	TRUE
Wave	Master	Open	700-746	4:00	14	6.1		TRUE	TRUE	TRUE
Wave	Cat 1/2/3	Women	100-131	4:40	14	6.1		TRUE	TRUE	TRUE
```

### --CrossMgr-Properties
```
Event Name	Event Organizer	Event City	Event StateProv	Event Country	Event Date	Scheduled Start	TimeZone	Race Number	Race Discipline	Enable RFID	Distance Unit	Time Trial	RFID Option	Use SFTP	FTP Host	FTP User	FTP Password	FTP Path	FTP Upload During Race	GATrackingID	Road Race Finish Times	No Data DNS	Win and Out	Event Long Name	Email	Google Maps API Key
Murchie Ciruit-1030	Thrashers	Langley	BC	Canada	2026-03-14	10:30	America/Vancouver	1	Road	TRUE	km	FALSE	0	FALSE		sl	<FTP_PASSWORD>		TRUE	UA-64955454-1	FALSE	TRUE	FALSE	Murchie-1030	drew@oh-water.com	<GOOGLE_MAPS_API_KEY>
```

## Usage
```
lapsrv.py --help | --xlsx [xlsx file] --crossmgr [Host[:port]] --port [server port] --web [web port] [--show_unknown_tags]
```
- crossmgr - crossmgr host, default is localhost, and port is 8765, e.g. localhost:8765 or

- port - port to listen for the Impinj4 program to send tag reads, default is 53136
- web - port to run the web server for the web interface, default is 8865
- show_unknown_tags - show unmatched tags using the first 12 characters of the EPC code; by default unmatched tags are ignored


## Notes

Lapsrv will:
- load the race configuration from the CrossMgr XLSX file to get the racer information, category
- implement a web server for the display
- implement a tkinter application for the display
- implement a JChip protocol server to receive the tag reads from the Impinj4 program
- connect to the CrossMgr WebSocket API's to get the current laps for each category 


## Other files
- Announcer.html - javascript code to connect to the CrossMgr WebSocket API for live results and display the information as a web page
- LapCounter.html - javascript code to connect to the CrossMgr WebSocket API for current laps
- CrossMgrServer.py - the Impinj4 class that connects to CrossMgr and implements the JChip protocol server to send the tag reads to CrossMgr
- JChip.py - the CrossMgr JChip protocol implementation to receive the tag reads to CrossMgr

CrossMgrServer is provided to show what the server will be expecting to receive and what it will be sending to CrossMgr. 
JChip is provided to show how the JChip protocol works and what the server will be expecting to receive and what it will be sending to Impinj4.

N.b. Use JChip as an example, but reimplement to fit into lapsrv.   




