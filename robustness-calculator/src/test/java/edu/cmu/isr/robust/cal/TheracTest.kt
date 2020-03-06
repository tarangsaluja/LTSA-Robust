package edu.cmu.isr.robust.cal

import edu.cmu.isr.robust.eofm.EOFMS
import edu.cmu.isr.robust.eofm.TheracNoWaitConfig
import edu.cmu.isr.robust.eofm.TheracRobustNoWaitConfig
import edu.cmu.isr.robust.eofm.parseEOFMS
import org.junit.jupiter.api.Test

class TheracTest {

  @Test
  fun theracTest() {
    val p = ClassLoader.getSystemResource("specs/therac25/p_w.lts").readText()
    val sys = ClassLoader.getSystemResource("specs/therac25/sys.lts").readText()
    val therac: EOFMS = parseEOFMS(ClassLoader.getSystemResourceAsStream("eofms/therac25_nowait.xml"))
    val config = TheracNoWaitConfig()
    val cal = EOFMRobustCal.create(sys, p, therac, config.initialValues, config.world, config.relabels)

    cal.computeRobustness()
  }

  @Test
  fun theracRedesignTest() {
    val p = ClassLoader.getSystemResource("specs/therac25/p_w.lts").readText()
    val sys = ClassLoader.getSystemResource("specs/therac25/sys_r.lts").readText()
    val therac: EOFMS = parseEOFMS(ClassLoader.getSystemResourceAsStream("eofms/therac25_nowait.xml"))
    val config = TheracRobustNoWaitConfig()
    val cal = EOFMRobustCal.create(sys, p, therac, config.initialValues, config.world, config.relabels)

    cal.computeRobustness()
  }

  @Test
  fun compareTheracAndRedesignTest() {
    val p = ClassLoader.getSystemResource("specs/therac25/p_w.lts").readText()
    val therac: EOFMS = parseEOFMS(ClassLoader.getSystemResourceAsStream("eofms/therac25_nowait.xml"))
    // Read therac
    val config = TheracNoWaitConfig()
    val sys1 = ClassLoader.getSystemResource("specs/therac25/sys.lts").readText()
    val cal1 = EOFMRobustCal.create(sys1, p, therac, config.initialValues, config.world, config.relabels)
    cal1.nameOfWA = "WA1"

    // Read therac robust
    val configR = TheracRobustNoWaitConfig()
    val sys2 = ClassLoader.getSystemResource("specs/therac25/sys_r.lts").readText()
    val cal2 = EOFMRobustCal.create(sys2, p, therac, configR.initialValues, configR.world, configR.relabels)
    println("Compute Delta(MR,E,P) - Delta(M,E,P)")
    cal2.robustnessComparedTo(cal1.getWA(), "WA1")
    println("Compute Delta(M,E,P) - Delta(MR,E,P)")
    cal1.robustnessComparedTo(cal2.getWA(), "WA")
  }

  @Test
  fun compareTwoPropertiesTest() {
    val therac: EOFMS = parseEOFMS(ClassLoader.getSystemResourceAsStream("eofms/therac25_nowait.xml"))
    val config = TheracNoWaitConfig()
    val sys = ClassLoader.getSystemResource("specs/therac25/sys.lts").readText()

    val pw = ClassLoader.getSystemResource("specs/therac25/p_w.lts").readText()
    val cal1 = EOFMRobustCal.create(sys, pw, therac, config.initialValues, config.world, config.relabels)

    val ps = ClassLoader.getSystemResource("specs/therac25/p_s.lts").readText()
    val cal2 = EOFMRobustCal.create(sys, ps, therac, config.initialValues, config.world, config.relabels)
    cal2.nameOfWA = "WA1"

    cal1.robustnessComparedTo(cal2.getWA(), "WA1")
  }

}