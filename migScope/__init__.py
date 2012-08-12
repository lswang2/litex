from migen.fhdl.structure import *
from migen.bus import csr
from migen.bank import description, csrgen
from migen.bank.description import *

class Term:
	def __init__(self, width, pipe=False):
		self.width = width
		self.pipe = pipe
		
		self.i = Signal(BV(self.width))
		self.t = Signal(BV(self.width))
		self.o = Signal()
	
	def get_fragment(self):
		frag = [
			self.o.eq(self.i==self.t)
			]
		if self.pipe:
			return Fragment(sync=frag)
		else:
			return Fragment(comb=frag)

class RangeDetector:
	def __init__(self, width, pipe=False):
		self.width = width
		self.pipe = pipe

		self.i = Signal(BV(self.width))
		self.low = Signal(BV(self.width))
		self.high = Signal(BV(self.width))
		self.o = Signal()
	
	def get_fragment(self):
		frag = [
			self.o.eq((self.i >= self.low) & ((self.i <= self.high)))
			]
		if self.pipe:
			return Fragment(sync=frag)
		else:
			return Fragment(comb=frag)

class EdgeDetector:
	def __init__(self, width, pipe=False, mode = "RFB"):
		self.width = width
		self.pipe = pipe
		self.mode = mode
		
		self.i = Signal(BV(self.width))
		self.i_d = Signal(BV(self.width))
		if "R" in mode:
			self.r_mask = Signal(BV(self.width))
			self.ro = Signal()
		if "F" in mode:
			self.f_mask = Signal(BV(self.width))
			self.fo = Signal()
		if "B" in mode:
			self.b_mask = Signal(BV(self.width))
			self.bo = Signal()
		self.o = Signal()
	
	def get_fragment(self):
		comb = []
		sync = []
		sync += [self.i_d.eq(self.i)]
		# Rising Edge
		if "R" in self.mode:
			if self.pipe:
				sync += [self.ro.eq(self.i & (~self.i_d))]
			else:
				comb +=  [self.ro.eq(self.i & (~ self.i_d))]
		else:
			comb +=  [self.ro.eq(0)]
		# Falling Edge
		if "F" in self.mode:
			if self.pipe:
				sync += [self.fo.eq((~ self.i) & self.i_d)]
			else:
				comb +=  [self.fo.eq((~ self.i) & self.i_d)]
		else:
			comb +=  [self.fo.eq(0)]
		# Both
		if "B" in self.mode:
			if self.pipe:
				sync += [self.bo.eq(self.i != self.i_d)]
			else:
				comb +=  [self.bo.eq(self.i != self.i_d)]
		else:
			comb +=  [self.bo.eq(0)]
		#Output
		comb +=  [self.o.eq(self.ro | self.fo | self.bo)]
		
		return Fragment(comb, sync)

class Timer:
	def __init__(self, width):
		self.width = width
		
		self.start = Signal()
		self.stop = Signal()
		self.clear = Signal()
		
		self.enable = Signal()
		self.cnt = Signal(BV(self.width))
		self.cnt_max = Signal(BV(self.width))
		
		self.o = Signal()

	def get_fragment(self):
		comb = []
		sync = []
		sync += [
			If(self.stop,
				self.enable.eq(0),
				self.cnt.eq(0),
				self.o.eq(0)
			).Elif(self.clear,
				self.cnt.eq(0),
				self.o.eq(0)
			).Elif(self.start,
				self.enable.eq(1)
			).Elif(self.enable,
				If(self.cnt <= self.cnt_max,
					self.cnt.eq(self.cnt+1)
				).Else(
					self.o.eq(1)
				)
			),
			If(self.enable,
				self.enable.eq(0),
				self.cnt.eq(0)
			).Elif(self.clear,
				self.cnt.eq(0)
			).Elif(self.start,
				self.enable.eq(1)
			)
			
			]
		
		return Fragment(comb, sync)

class Sum:
	def __init__(self,size=4,pipe=False,prog_mode="PAR"):
		self.size = size
		self.pipe = pipe
		self.prog_mode = prog_mode
		assert (size <= 4), "size > 4 (This version support only non cascadable SRL16)"
		self.i = Array(Signal() for j in range(4))
		for j in range(4):
			self.i[j].name_override = "i%d"%j
		
		self._ce = Signal()
		self._shift_in = Signal()
		
		self.o = Signal()
		self._o = Signal()
		
		if self.prog_mode == "PAR":
			self.prog =  Signal()
			self.prog_dat = Signal(BV(16))
			self._shift_dat = Signal(BV(17))
			self._shift_cnt = Signal(BV(4))
		elif self.prog_mode == "SHIFT":
			self.shift_ce = Signal()
			self.shift_in = Signal()
			self.shift_out = Signal()
		
		
	def get_fragment(self):
		_shift_out = Signal()
		comb = []
		sync = []
		if self.prog_mode == "PAR":
			sync += [
				If(self.prog,
					self._shift_dat.eq(self.prog_dat),
					self._shift_cnt.eq(16)
				),
			
				If(self._shift_cnt != 0,
					self._shift_dat.eq(self._shift_dat[1:]),
					self._shift_cnt.eq(self._shift_cnt-1),
					self._ce.eq(1)
				).Else(
					self._ce.eq(0)
				)
				]
			comb += [
				self._shift_in.eq(self._shift_dat[0])
				]
		elif self.prog_mode == "SHIFT":
			comb += [
				self._ce.eq(self.shift_ce),
				self._shift_in.eq(self.shift_in)
				]
		inst = [
			Instance("SRLC16E",
				[
				("a0", self.i[0]),
				("a1", self.i[1]),
				("a2", self.i[2]),
				("a3", self.i[3]),
				("ce", self._ce),
				("d", self._shift_in)
				] , [
				("q", self._o),
				("q15",_shift_out)
				] ,
				clkport="clk",
			)
		]
		if self.prog_mode == "SHIFT":
			comb += [
				self.shift_out.eq(_shift_out)
				]
		if self.pipe:
			sync += [self.o.eq(self._o)]
		else:
			comb += [self.o.eq(self._o)]
		return Fragment(comb=comb,sync=sync,instances=inst)
		

class Trigger:
	def __init__(self,address, trig_width, dat_width, ports):
		self.trig_width = trig_width
		self.dat_width = dat_width
		self.ports = ports
		assert (len(self.ports) <= 4), "Nb Ports > 4 (This version support 4 ports Max)"
		
		self.in_trig = Signal(BV(self.trig_width))
		self.in_dat  = Signal(BV(self.dat_width))
		
		self.hit = Signal()
		self.dat = Signal(BV(self.dat_width))
		
		
	def get_fragment(self):
		comb = []
		sync = []
		# Connect in_trig to input of trig elements
		comb+= [port.i.eq(self.in_trig) for port in self.ports]
		
		# Connect output of trig elements to sum
		# Todo : Add sum tree to have more that 4 inputs
		_sum = Sum(len(self.ports))
		comb+= [_sum.i[j].eq(self.ports[j].o) for j in range(len(self.ports))]
		
		# Connect sum ouput to hit
		comb+= [self.hit.eq(_sum.o)]
		
		# Add ports & sum to frag
		frag = _sum.get_fragment()
		for port in self.ports:
			frag += port.get_fragment()

		
		comb+= [self.dat.eq(self.in_dat)]
		
		return frag + _sum.get_fragment() + Fragment(comb=comb, sync=sync)


class Storage:
	def __init__(self, width, depth):
		self.width = width
		self.depth = depth
		self.depth_width = bits_for(self.depth)
		#Control
		self.rst = Signal()
		self.start = Signal()
		self.offset = Signal(BV(self.depth_width))
		self.size = Signal(BV(self.depth_width))
		self.done = Signal()
		#Write Path
		self.put = Signal()
		self.put_dat = Signal(BV(self.width))
		self._put_cnt = Signal(BV(self.depth_width))
		self._put_ptr = Signal(BV(self.depth_width))
		self._put_port = MemoryPort(adr=self._put_ptr, we=self.put, dat_w=self.put_dat)
		#Read Path
		self.get = Signal()
		self.get_dat = Signal(BV(self.width))
		self._get_cnt = Signal(BV(self.depth_width))
		self._get_ptr = Signal(BV(self.depth_width))
		self._get_port = MemoryPort(adr=self._get_ptr, re=self.get, dat_r=self.get_dat)
		#Others
		self._mem = Memory(self.width, self.depth, self._put_port, self._get_port)
		
		
	def get_fragment(self):
		comb = []
		sync = []
		memories = [self._mem]
		size_minus_offset = Signal(BV(self.depth_width))
		comb += [size_minus_offset.eq(self.size-self.offset)]
		
		#Control
		sync += [
			If(self.rst,
				self._put_cnt.eq(0),
				self._put_ptr.eq(0),
				self._get_cnt.eq(0),
				self._get_ptr.eq(0),
				self.done.eq(0)
			).Elif(self.start,
				self._put_cnt.eq(0),
				self._get_cnt.eq(0),
				self._get_ptr.eq(self._put_ptr-size_minus_offset)
			),
			If(self.put,
				self._put_cnt.eq(self._put_cnt+1),
				self._put_ptr.eq(self._put_ptr+1)
			),
			If(self.get,
				self._get_cnt.eq(self._get_cnt+1),
				self._get_ptr.eq(self._get_ptr+1)
			)
			]
		comb += [
			If(self._put_cnt == size_minus_offset-1,
				self.done.eq(1)
			).Elif(self._get_cnt == size_minus_offset-1,
				self.done.eq(1)
			).Else(
				self.done.eq(0)
			)
			]
		return Fragment(comb=comb, sync=sync, memories=memories)

class Sequencer:
	def __init__(self,depth):
		self.depth = depth
		self.depth_width = bits_for(self.depth)
		# Controller interface
		self.ctl_rst = Signal()
		self.ctl_offset = Signal(BV(self.depth_width))
		self.ctl_size = Signal(BV(self.depth_width))
		self.ctl_arm = Signal()
		self.ctl_done = Signal()
		# Triggers interface
		self.trig_hit  = Signal()
		# Recorder interface
		self.rec_offset = Signal(BV(self.depth_width))
		self.rec_size = Signal(BV(self.depth_width))
		self.rec_start = Signal()
		self.rec_done  = Signal()
		# Others
		self.enable = Signal()
		
	def get_fragment(self):
		comb = []
		sync = []
		#Control
		sync += [
			If(self.ctl_rst,
				self.enable.eq(0)
			).Elif(self.ctl_arm,
				self.enable.eq(1)
			).Elif(self.rec_done,
				self.enable.eq(0)
			)
			]
		comb += [
			self.rec_offset.eq(self.ctl_offset),
			self.rec_size.eq(self.ctl_size),
			self.rec_start.eq(self.enable & self.trig_hit),
			self.ctl_done.eq(~self.enable)
			]
		return Fragment(comb=comb, sync=sync)

class Recorder:
	def __init__(self,address, width, depth):
		self.address = address
		self.width = width
		self.depth = depth
		self.depth_width = bits_for(self.depth)
		
		self.storage = Storage(self.width, self.depth)
		self.sequencer = Sequencer(self.depth)
		
		# Csr interface
		self._rst = RegisterField("rst", reset=1)
		self._arm = RegisterField("arm", reset=0)
		self._done = RegisterField("done", reset=0, access_bus=READ_ONLY, access_dev=WRITE_ONLY)
		
		self._size = RegisterField("size", self.depth_width, reset=1)
		self._offset = RegisterField("offset", self.depth_width, reset=1)
		
		self._get = RegisterField("get", reset=1)
		self._get_dat = RegisterField("get_dat", self.width, reset=1,access_bus=READ_ONLY, access_dev=WRITE_ONLY)
		
		regs = [self._rst, self._arm, self._done,
			self._size, self._offset,
			self._get, self._get_dat]
			
		self.bank = csrgen.Bank(regs,address=address)
		
		# Trigger Interface
		self.trig_hit = Signal()
		self.trig_dat = Signal(BV(self.width))
		
	def get_fragment(self):
		comb = []
		sync = []
		#Bank <--> Storage / Sequencer
		comb += [
			self.sequencer.ctl_rst.eq(self._rst.field.r),
			self.storage.rst.eq(self._rst.field.r),
			self.sequencer.ctl_offset.eq(self._offset.field.r),
			self.sequencer.ctl_size.eq(self._size.field.r),
			self.sequencer.ctl_arm.eq(self._arm.field.r),
			self._done.field.w.eq(self.sequencer.ctl_done)
			]
		
		#Storage <--> Sequencer <--> Trigger
		comb += [
			self.storage.offset.eq(self.sequencer.rec_offset),
			self.storage.size.eq(self.sequencer.rec_size),
			self.storage.start.eq(self.sequencer.rec_start),
			self.sequencer.rec_done.eq(self.storage.done),
			self.sequencer.trig_hit.eq(self.trig_hit),
			self.storage.put.eq(self.sequencer.enable),
			self.storage.put_dat.eq(self.trig_dat)
			
			]

		return self.bank.get_fragment()+\
			self.storage.get_fragment()+self.sequencer.get_fragment()+\
			Fragment(comb=comb, sync=sync)
			



class MigCon:
	pass
	
class MigLa:
	pass

class MigIo:
	def __init__(self, width, mode = "IO"):
		self.width = width
		self.mode = mode
		self.ireg = description.RegisterField("i", 0, READ_ONLY, WRITE_ONLY)
		self.oreg = description.RegisterField("o", 0)
		if "I" in self.mode:
			self.inputs = Signal(BV(self.width))
			self.ireg = description.RegisterField("i", self.width, READ_ONLY, WRITE_ONLY)
			self.ireg.field.w.name_override = "inputs"
		if "O" in self.mode:
			self.outputs = Signal(BV(self.width))
			self.oreg = description.RegisterField("o", self.width)
			self.oreg.field.r.name_override = "ouptuts"
		self.bank = csrgen.Bank([self.oreg, self.ireg])

	def get_fragment(self):
		return self.bank.get_fragment()